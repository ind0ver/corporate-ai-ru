from dotenv import load_dotenv
import os

load_dotenv()

# LLM
LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:11434") # Ollama
# LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:8002") # vLLM

MODEL = os.getenv("MODEL", "gemma4:e4b")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "Ты - полезный корпоративный ассистент компании SideWays.")

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_SESSION_TTL = int(os.getenv("REDIS_SESSION_TTL", "86400"))
REDIS_MAX_HISTORY = int(os.getenv("REDIS_MAX_HISTORY", "20"))

# Embeddings
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge_base")

# Адрес backend для frontend-а
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

# SQL Database
DATABASE_URL=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")
# DATABASE_URL=os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@postgres/db")