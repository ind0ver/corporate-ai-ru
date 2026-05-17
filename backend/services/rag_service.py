from rag.retrieval import search_docs
from backend.services.prompt_builder import build_prompt
from backend.services.llm_service import generate_stream
from backend.services.session_service import load_history, save_turn
from backend.schemas import ChatRequest
from backend.config import SYSTEM_PROMPT


async def ask_stream(chat_request: ChatRequest):
    try:
        history = await load_history(chat_request.session_id)
    except Exception:
        history = []  # Redis недоступен — работаем без истории
    
    try:
        docs = search_docs(chat_request.message)
    except Exception:
        docs = []  # Qdrant недоступен — работаем без контекста

    prompt = build_prompt(
        question=chat_request.message,
        context=docs,
        history=history
    )

    system_prompt = chat_request.system_prompt or SYSTEM_PROMPT
    answer = ""

    async for token in generate_stream(
        prompt=prompt,
        model=chat_request.model,
        system_prompt=system_prompt,
        temperature=chat_request.temperature
    ):
        answer += token
        yield token

    # save_turn после того как стрим завершён
    try:
        await save_turn(
            user_id=chat_request.user_id,
            session_id=chat_request.session_id,
            user_msg=chat_request.message,
            assistant_msg=answer
        )
    except Exception as e:
        print(f"Ошибка сохранения сессии: {e}")
