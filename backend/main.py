import uuid
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from backend.schemas import (
    ChatRequest, ChatResponse,
    UserInfo, CreateUserRequest,
    SessionInfo, CreateSessionRequest,
)
from backend.services.rag_service import ask_stream
from backend.services.session_service import (
    get_users, register_user, get_user_name,
    get_sessions, register_session,
    load_history,
)
from backend.startup import run_startup_checks, StartupError
from backend.health import router as health_router
from backend.services.llm_service import get_available_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup_checks()
    yield
    print("👋 Сервер останавливается")


app = FastAPI(lifespan=lifespan)
app.include_router(health_router)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.get("/users", response_model=list[UserInfo])
async def list_users():
    """Список всех пользователей из Redis."""
    return await get_users()


@app.post("/users", response_model=UserInfo, status_code=201)
async def create_user(body: CreateUserRequest):
    """Создаёт нового пользователя, возвращает user_id + имя."""
    user_id = str(uuid.uuid4())
    name = body.name.strip() or user_id[:8]
    await register_user(user_id, name)
    return UserInfo(user_id=user_id, name=name)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/sessions", response_model=list[SessionInfo])
async def list_sessions(user_id: str):
    """Список сессий пользователя, новые первыми."""
    sessions = await get_sessions(user_id)
    return [SessionInfo(session_id=s) for s in sessions]


@app.post("/users/{user_id}/sessions", response_model=SessionInfo, status_code=201)
async def create_session(user_id: str):
    """Создаёт новую сессию для пользователя."""
    session_id = str(uuid.uuid4())
    await register_session(user_id, session_id)
    return SessionInfo(session_id=session_id)


@app.get("/sessions/{session_id}/history")
async def get_history(session_id: str):
    """История чата для сессии — используется UI при переключении сессий."""
    history = await load_history(session_id)
    return {"session_id": session_id, "history": history}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/chat/stream")
async def chat_stream(chat_request: ChatRequest):

    async def event_stream():
        try:
            async for token in ask_stream(chat_request):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

@app.get("/models")
async def get_models():
    return get_available_models()
