import asyncio
import logging
from functools import lru_cache
from typing import Optional

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sentence_transformers import SentenceTransformer

from backend.config import (
    EMBEDDING_MODEL,
    QDRANT_COLLECTION,
    QDRANT_HOST,
    QDRANT_PORT,
)

logger = logging.getLogger(__name__)

# Минимальный score для включения документа в контекст.
SCORE_THRESHOLD = 0.35

_embedder: Optional[SentenceTransformer] = None
_qdrant: Optional[AsyncQdrantClient] = None

# Флаг, что коллекция существует
_collection_verified: bool = False


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _embedder


def get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            timeout=10,
        )
    return _qdrant


async def _ensure_collection(collection: str) -> bool:
    """Проверяет существование коллекции один раз и кеширует результат.
    """
    global _collection_verified
    if _collection_verified:
        return True

    try:
        client = get_qdrant()
        collections = await client.get_collections()
        names = [c.name for c in collections.collections]

        if collection not in names:
            logger.error(
                "Qdrant collection '%s' not found. Available: %s",
                collection, names,
            )
            return False

        _collection_verified = True
        logger.info("Qdrant collection '%s' verified", collection)
        return True

    except Exception as exc:
        logger.error("Failed to verify Qdrant collection: %s", exc)
        return False


async def search_docs(query: str, top_k: int = 5) -> list[str]:
    """Ищет релевантные документы в Qdrant по семантическому сходству.

    Args:
        query:  Текст запроса пользователя.
        top_k:  Максимальное кол-во документов для возврата.

    Returns:
        Список текстов чанков, отсортированных по убыванию score.
        Возвращает [] если коллекция не найдена или Qdrant недоступен.
    """
    if not await _ensure_collection(QDRANT_COLLECTION):
        return []

    try:
        # SentenceTransformer.encode() — CPU-bound, синхронный.
        # run_in_executor не блокирует event loop — другие запросы обрабатываются параллельно.
        loop = asyncio.get_running_loop()
        embedder = _get_embedder()
        vec: list[float] = await loop.run_in_executor(
            None,  # default ThreadPoolExecutor
            lambda: embedder.encode(query).tolist(),
        )

        client = get_qdrant()
        result = await client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vec,
            limit=top_k,
            score_threshold=SCORE_THRESHOLD,
        )

        texts: list[str] = []
        for point in result.points:
            if not point.payload:
                logger.warning("Point %s has no payload, skipping", point.id)
                continue
            text = point.payload.get("text")
            if text:
                texts.append(text)
            else:
                logger.warning("Point %s payload has no 'text' field", point.id)

        logger.debug(
            "search_docs: query='%s' top_k=%d found=%d",
            query[:60], top_k, len(texts),
        )
        return texts

    except UnexpectedResponse as exc:
        # Коллекция удалена после старта — сбрасываем кеш чтобы перепроверить
        global _collection_verified
        _collection_verified = False
        logger.error("Qdrant UnexpectedResponse during search: %s", exc)
        return []

    except Exception as exc:
        logger.error("search_docs failed: %s", exc, exc_info=True)
        return []


async def close_qdrant() -> None:
    """Закрывает соединение с Qdrant при остановке приложения.
    """
    global _qdrant
    if _qdrant is not None:
        await _qdrant.close()
        _qdrant = None
        logger.info("Qdrant client closed")