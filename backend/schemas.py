from pydantic import BaseModel
from typing import Optional, List


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.2
    top_k: int = 5


class ResponseSource(BaseModel):
    source: str
    page: int
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: List[ResponseSource] = []
    session_id: str
    latency_ms: int


# ---------------------------------------------------------------------------
# Users & Sessions
# ---------------------------------------------------------------------------

class UserInfo(BaseModel):
    user_id: str
    name: str


class CreateUserRequest(BaseModel):
    name: str = ""   # если пусто — покажем короткий UUID


class SessionInfo(BaseModel):
    session_id: str


class CreateSessionRequest(BaseModel):
    pass  # session_id генерируется на сервере