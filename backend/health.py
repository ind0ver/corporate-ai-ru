import time
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.config import LLM_API_URL, MODEL
from backend.services.session_service import get_redis
from backend.rag.retrieval import get_qdrant


router = APIRouter(tags=["health"])

# Время старта — для uptime
_start_time = time.time()


class DependencyStatus(BaseModel):
    status: str        # "ok" | "error"
    latency_ms: float
    detail: str = ""


class HealthResponse(BaseModel):
    status: str        # "ok" | "degraded" | "error"
    uptime_seconds: float
    dependencies: dict[str, DependencyStatus]


async def _probe_redis() -> DependencyStatus:
    t = time.monotonic()
    try:
        client = get_redis()
        await client.ping()
        await client.aclose()
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        return DependencyStatus(status="error", latency_ms=0, detail=str(e))


async def _probe_qdrant() -> DependencyStatus:
    t = time.monotonic()
    try:
        client = get_qdrant()
        await client.get_collections()
        await client.close()
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        return DependencyStatus(status="error", latency_ms=0, detail=str(e))


async def _check_openai_compatible() -> None:
    t = time.monotonic()
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
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        raise DependencyStatus(status="error", latency_ms=0, detail=f"OpenAI‑compatible API недоступна ({LLM_API_URL}): {e}")
    

@router.get("/health", response_model=HealthResponse)
async def liveness():
    """
    Liveness probe — приложение живо?
    Kubernetes использует это чтобы решить, перезапускать ли pod.
    Намеренно лёгкий: не проверяет зависимости.
    """
    return HealthResponse(
        status="ok",
        uptime_seconds=round(time.time() - _start_time, 2),
        dependencies={}
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness():
    """
    Readiness probe — готово ли приложение принимать трафик?
    Kubernetes снимает pod из балансировщика если этот эндпоинт возвращает не 200.
    Проверяет все зависимости.
    """
    deps = {
        "redis":  await _probe_redis(),
        "qdrant": await _probe_qdrant(),
        "llm": await _check_openai_compatible(),
    }

    all_ok = all(d.status == "ok" for d in deps.values())
    overall = "ok" if all_ok else "degraded"

    return HealthResponse(
        status=overall,
        uptime_seconds=round(time.time() - _start_time, 2),
        dependencies=deps,
    )