from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from backend.config import EMBEDDING_MODEL, QDRANT_COLLECTION, QDRANT_HOST, QDRANT_PORT
import os

# Инициализация эмбеддинг‑модели
embedder = SentenceTransformer(EMBEDDING_MODEL)

# Подключение к серверу Qdrant
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def search_docs(query: str) -> list:
    # print("=" * 80)
    # print("НАЧАЛО ПОИСКА")
    # print(f"Запрос: {query}")
    # print(f"Хост qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    # print(f"Имя коллекции: {QDRANT_COLLECTION}")

    # Создаём эмбеддинг запроса
    vec = embedder.encode(query).tolist()
    # print(f"Размер вектора эмбеддинга: {len(vec)}")
    # print(f"Первые 5 элементов вектора: {vec[:5]}")

    try:
        # Проверяем, существует ли коллекция
        collections = qdrant.get_collections().collections
        collection_names = [c.name for c in collections]
        # print(f"Доступные коллекции на сервере: {collection_names}")

        if QDRANT_COLLECTION not in collection_names:
            print(f"ОШИБКА: Коллекция '{QDRANT_COLLECTION}' не найдена на сервере!")
            print("Доступные коллекции:", collection_names)
            return []

        # print(f"Коллекция '{QDRANT_COLLECTION}' найдена, выполняем поиск...")

        # Поиск в коллекции Qdrant
        result = qdrant.query_points(
            collection_name=QDRANT_COLLECTION,
            query=vec,
            limit=5
        )

        # Вывод результатов (для отладки)
        found_texts = []
        for i, point in enumerate(result.points):
            # print("-" * 40)
            # print(f"Результат #{i + 1}")
            # print("score:", point.score)
            if point.payload:
                # print("source:", point.payload.get("source", "N/A"))
                # print("page:", point.payload.get("page", "N/A"))
                text_preview = point.payload.get("text", "")[:500]
                # print(f"текст (превью): {text_preview}")
                found_texts.append(point.payload["text"])
            else:
                print("payload отсутствует!")

        if not found_texts:
            print("ПРЕДУПРЕЖДЕНИЕ: Поиск не вернул текстов, хотя результаты найдены (возможно, payload пуст)")

        return found_texts

    except Exception as e:
        print(f"ИСКЛЮЧЕНИЕ ПРИ ПОИСКЕ: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []
