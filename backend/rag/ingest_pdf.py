import uuid
import fitz
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from qdrant_client.http.models import Distance, VectorParams
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.config import EMBEDDING_MODEL, QDRANT_COLLECTION, QDRANT_HOST, QDRANT_PORT


def ingest_pdf(collection_name, chunk_size=1024, chunk_overlap=256):

    embedder = SentenceTransformer(EMBEDDING_MODEL)
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    points = []

    for pdf_file in Path("docs").glob("*.pdf"):

        doc = fitz.open(pdf_file)

        for page_num, page in enumerate(doc, start=1):

            text = page.get_text("text")

            if not text.strip():
                continue

            chunks = splitter.split_text(text)

            for chunk in chunks:

                vec = embedder.encode(chunk).tolist()

                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vec,
                        payload={
                            "text": chunk,
                            "source": pdf_file.name,
                            "page": page_num
                        }
                    )
                )

    collections = qdrant.get_collections().collections
    collection_names = [collection.name for collection in collections]

    if collection_name not in collection_names:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
    
    qdrant.upsert(
        collection_name=collection_name,
        points=points
    )
    qdrant.close()
    print(f"Collection {QDRANT_COLLECTION} created")


if __name__ == "__main__":
    ingest_pdf(QDRANT_COLLECTION)
