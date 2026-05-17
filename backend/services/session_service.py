import json
import time
from redis.asyncio import Redis
from backend.config import REDIS_URL, REDIS_SESSION_TTL, REDIS_MAX_HISTORY


redis = Redis.from_url(REDIS_URL, decode_responses=True)

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
    Идемпотентно — повторный вызов только обновляет score.
    """
    await redis.zadd(USERS_ZSET, {user_id: time.time()})
    if name:
        await redis.set(_name_key(user_id), name)


async def get_users() -> list[dict]:
    """Возвращает пользователей отсортированных по последней активности (новые первыми)."""
    user_ids = await redis.zrevrange(USERS_ZSET, 0, -1)
    result = []
    for uid in user_ids:
        name = await redis.get(_name_key(uid)) or uid[:8]
        result.append({"user_id": uid, "name": name})
    return result


async def get_user_name(user_id: str) -> str:
    return await redis.get(_name_key(user_id)) or user_id[:8]


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

async def register_session(user_id: str, session_id: str) -> None:
    """Регистрирует сессию и обновляет активность пользователя."""
    await register_user(user_id)  # обновляет timestamp пользователя
    await redis.zadd(_sessions_key(user_id), {session_id: time.time()})
    await redis.expire(_sessions_key(user_id), REDIS_SESSION_TTL)


async def get_sessions(user_id: str) -> list[str]:
    """Возвращает session_id пользователя, новые первыми."""
    sessions = await redis.zrevrange(_sessions_key(user_id), 0, -1)
    return list(sessions)


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

async def load_history(session_id: str) -> list[dict]:
    data = await redis.get(_chat_key(session_id))
    if not data:
        return []
    return json.loads(data)


async def save_turn(
    session_id: str,
    user_id: str,
    user_msg: str,
    assistant_msg: str,
) -> None:
    """Сохраняет диалоговый ход и обновляет активность пользователя/сессии."""
    history = await load_history(session_id)

    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    history = history[-REDIS_MAX_HISTORY:]

    await redis.set(
        _chat_key(session_id),
        json.dumps(history, ensure_ascii=False),
        ex=REDIS_SESSION_TTL,
    )
    # Поднимаем пользователя и сессию наверх списка
    await register_session(user_id, session_id)


async def clear_history(session_id: str) -> None:
    await redis.delete(_chat_key(session_id))
