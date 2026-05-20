import json
import logging
import time
from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError
from backend.config import REDIS_URL, REDIS_SESSION_TTL, REDIS_MAX_HISTORY


logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    """Инициализирует пул один раз.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=20,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
    return _pool


def get_redis() -> Redis:
    """Возвращает Redis-клиент, использующий общий пул.
    """
    return Redis(connection_pool=_get_pool())


async def close_redis_pool() -> None:
    """Закрывает пул при остановке приложения.
    """
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("Redis connection pool closed")

# ---------------------------------------------------------------------------
# Redis key schema
# ---------------------------------------------------------------------------
# users_by_activity             — ZSET user_id → timestamp (новые = выше score)
# user:{user_id}:sessions       — ZSET session_id → timestamp
# user:{user_id}:name           — STRING отображаемое имя
# chat:{session_id}             — STRING JSON-история чата

USERS_ZSET = "users_by_activity"


def _chat_key(session_id: str) -> str:
    return f"chat:{session_id}"


def _sessions_key(user_id: str) -> str:
    return f"user:{user_id}:sessions"


def _name_key(user_id: str) -> str:
    return f"user:{user_id}:name"

# ---------------------------------------------------------------------------
# User registry
# ---------------------------------------------------------------------------

async def register_user(user_id: str, name: str = "") -> None:
    """Регистрирует пользователя и обновляет timestamp активности.
    """
    r = get_redis()
    try:
        async with r.pipeline(transaction=True) as pipe:
            pipe.zadd(USERS_ZSET, {user_id: time.time()})
            if name:
                pipe.set(_name_key(user_id), name)
            await pipe.execute()
    except RedisError as exc:
        logger.error("register_user failed: user_id=%s error=%s", user_id, exc)
        raise


async def get_users() -> list[dict]:
    """Возвращает пользователей, отсортированных по последней активности (новые первыми)."""
    r = get_redis()
    try:
        user_ids: list[str] = await r.zrevrange(USERS_ZSET, 0, -1)
    except RedisError as exc:
        logger.error("get_users zrevrange failed: %s", exc)
        return []

    if not user_ids:
        return []

    result: list[dict] = []
    try:
        async with r.pipeline(transaction=False) as pipe:
            for uid in user_ids:
                pipe.get(_name_key(uid))
            names: list[Optional[str]] = await pipe.execute()

        for uid, name in zip(user_ids, names):
            result.append({"user_id": uid, "name": name or uid[:8]})
    except RedisError as exc:
        logger.error("get_users pipeline failed: %s", exc)
        return [{"user_id": uid, "name": uid[:8]} for uid in user_ids]

    return result


async def get_user_name(user_id: str) -> str:
    r = get_redis()
    try:
        name: Optional[str] = await r.get(_name_key(user_id))
        return name or user_id[:8]
    except RedisError as exc:
        logger.warning("get_user_name failed: user_id=%s error=%s", user_id, exc)
        return user_id[:8]

# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

async def register_session(user_id: str, session_id: str) -> None:
    """Регистрирует сессию и обновляет активность пользователя."""
    r = get_redis()
    now = time.time()
    try:
        async with r.pipeline(transaction=True) as pipe:
            # Обновляем активность пользователя
            pipe.zadd(USERS_ZSET, {user_id: now})
            # Добавляем сессию
            pipe.zadd(_sessions_key(user_id), {session_id: now})
            # Обновляем TTL сессий
            pipe.expire(_sessions_key(user_id), REDIS_SESSION_TTL)
            await pipe.execute()
    except RedisError as exc:
        logger.error(
            "register_session failed: user_id=%s session_id=%s error=%s",
            user_id, session_id, exc,
        )
        raise


async def get_sessions(user_id: str) -> list[str]:
    """Возвращает session_id пользователя, новые первыми."""
    r = get_redis()
    try:
        sessions: list[str] = await r.zrevrange(_sessions_key(user_id), 0, -1)
        return list(sessions)
    except RedisError as exc:
        logger.error("get_sessions failed: user_id=%s error=%s", user_id, exc)
        return []

# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

async def load_history(session_id: str) -> list[dict]:
    r = get_redis()
    try:
        data: Optional[str] = await r.get(_chat_key(session_id))
        if not data:
            return []
        return json.loads(data)
    except RedisError as exc:
        logger.error("load_history failed: session_id=%s error=%s", session_id, exc)
        return []
    except json.JSONDecodeError as exc:
        logger.error("load_history json decode failed: session_id=%s error=%s", session_id, exc)
        return []


async def save_turn(
    session_id: str,
    user_id: str,
    user_msg: str,
    assistant_msg: str,
) -> None:
    """Сохраняет диалоговый ход и обновляет активность пользователя/сессии.
    """
    history = await load_history(session_id)

    history.append({"role": "user",      "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})

    history = history[-REDIS_MAX_HISTORY:]

    serialized = json.dumps(history, ensure_ascii=False)
    now = time.time()
    r = get_redis()

    try:
        async with r.pipeline(transaction=True) as pipe:
            # История чата
            pipe.set(_chat_key(session_id), serialized, ex=REDIS_SESSION_TTL)
            # Активность пользователя
            pipe.zadd(USERS_ZSET, {user_id: now})
            # Активность сессии
            pipe.zadd(_sessions_key(user_id), {session_id: now})
            pipe.expire(_sessions_key(user_id), REDIS_SESSION_TTL)
            await pipe.execute()
    except RedisError as exc:
        # Логируем, но не роняем стрим — ответ пользователь уже получил
        logger.error(
            "save_turn failed: session_id=%s user_id=%s error=%s",
            session_id, user_id, exc,
        )
        raise


async def clear_history(session_id: str) -> None:
    r = get_redis()
    try:
        await r.delete(_chat_key(session_id))
    except RedisError as exc:
        logger.error("clear_history failed: session_id=%s error=%s", session_id, exc)
        raise
