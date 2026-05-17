import time
import httpx
import redis.asyncio as aioredis
from qdrant_client import AsyncQdrantClient
from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import REDIS_URL, QDRANT_HOST, QDRANT_PORT, LLM_API_URL

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
        client = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await client.ping()
        await client.aclose()
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        return DependencyStatus(status="error", latency_ms=0, detail=str(e))


async def _probe_qdrant() -> DependencyStatus:
    t = time.monotonic()
    try:
        client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=2)
        await client.get_collections()
        await client.close()
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        return DependencyStatus(status="error", latency_ms=0, detail=str(e))


async def _probe_ollama() -> DependencyStatus:
    t = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{LLM_API_URL}/api/tags")
            r.raise_for_status()
        return DependencyStatus(status="ok", latency_ms=round((time.monotonic() - t) * 1000, 2))
    except Exception as e:
        return DependencyStatus(status="error", latency_ms=0, detail=str(e))


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
        "ollama": await _probe_ollama(),
    }

    all_ok = all(d.status == "ok" for d in deps.values())
    overall = "ok" if all_ok else "degraded"

    return HealthResponse(
        status=overall,
        uptime_seconds=round(time.time() - _start_time, 2),
        dependencies=deps,
    )