import httpx
import redis.asyncio as redis
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Dict, Any
from backend.config import (
    REDIS_URL,
    QDRANT_HOST, QDRANT_PORT,
    LLM_API_URL, MODEL,
)


class StartupError(Exception):
    """Критическая зависимость недоступна при старте."""


async def check_redis() -> None:
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        print("✅ Redis: OK")
    except Exception as e:
        raise StartupError(f"Redis недоступен ({REDIS_URL}): {e}")


async def check_qdrant() -> None:
    try:
        client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=3, check_compatibility=False)
        await client.get_collections()
        await client.close()
        print("✅ Qdrant: OK")
    except Exception as e:
        raise StartupError(f"Qdrant недоступен ({QDRANT_HOST}:{QDRANT_PORT}): {e}")


async def check_ollama() -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{LLM_API_URL}/api/tags")
            r.raise_for_status()

            models = [m["model"] for m in r.json().get("models", [])]
            if MODEL not in models:
                # Не критично — предупреждаем, но не падаем
                print(f"⚠️  Ollama: модель '{MODEL}' не найдена. Доступны: {models}")
            else:
                print(f"✅ Ollama: OK (модель '{MODEL}' найдена)")
    except Exception as e: 
        raise StartupError(f"Ollama недоступна ({LLM_API_URL}): {e}")


async def check_openai_compatible() -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # Запрос к эндпоинту /v1/models для OpenAI‑совместимых API
            r = await client.get(f"{LLM_API_URL}/v1/models")
            r.raise_for_status()

            # Парсим JSON и извлекаем список моделей
            response_data: Dict[str, Any] = r.json()
            models_data: List[Dict[str, Any]] = response_data.get("data", [])

            # Извлекаем имена моделей из поля "id" каждой записи
            models: List[str] = [m["id"] for m in models_data]

            if MODEL not in models:
                # Не критично — предупреждаем, но не падаем
                print(f"⚠️  OpenAI‑compatible API: модель '{MODEL}' не найдена. Доступны: {models}")
            else:
                print(f"✅ OpenAI‑compatible API: OK (модель '{MODEL}' найдена)")
    except Exception as e:
        raise StartupError(f"OpenAI‑compatible API недоступна ({LLM_API_URL}): {e}")


async def run_startup_checks() -> None:
    """
    Запускает все проверки последовательно.
    При первой же ошибке бросает StartupError — приложение не стартует.
    """
    print("🔍 Проверка зависимостей...")
    await check_redis()
    await check_qdrant()
    # await check_ollama()
    await check_openai_compatible()
    print("✅ Все зависимости доступны, сервер запускается\n")