import logging
from backend.config import MODEL, SYSTEM_PROMPT
from backend.schemas import ChatRequest
from backend.services.llm_service import generate_stream
from backend.services.session_service import load_history, save_turn
from backend.services.prompt_builder import build_prompt
from rag.retrieval import search_docs


logger = logging.getLogger(__name__)


async def ask_stream(chat_request: ChatRequest):
    # -- История ----------------------------------------------------------
    try:
        history = await load_history(chat_request.session_id)
    except Exception as exc:
        logger.warning("Could not load history, proceeding without it: %s", exc)
        history = []

    # -- RAG: поиск документов --------------------------------------------
    try:
        docs = await search_docs(chat_request.message, top_k=chat_request.top_k)
    except Exception as exc:
        logger.warning("RAG search failed, proceeding without context: %s", exc)
        docs = []

    # -- Промпт -----------------------------------------------------------
    prompt = build_prompt(
        question=chat_request.message,
        context=docs,
        history=history,
    )

    system_prompt = chat_request.system_prompt or SYSTEM_PROMPT

    model = chat_request.model
    if not model:
        raise ValueError("No model specified!")

    # -- Стрим LLM --------------------------------------------------------
    answer = ""
    async for token in generate_stream(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        temperature=chat_request.temperature,
    ):
        answer += token
        yield token

    # -- Сохраняем ход после завершения стрима ----------------------------
    try:
        await save_turn(
            user_id=chat_request.user_id,
            session_id=chat_request.session_id,
            user_msg=chat_request.message,
            assistant_msg=answer,
        )
    except Exception as exc:
        # Не роняем — пользователь уже получил ответ
        logger.error(
            "save_turn failed: session_id=%s error=%s",
            chat_request.session_id, exc,
        )
