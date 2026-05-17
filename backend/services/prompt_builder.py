from typing import List
from backend.config import REDIS_MAX_HISTORY


def build_prompt(question: str, context: List[str], history: List[dict]) -> str:
    joined_context = "\n\n".join(context)

    history_text = ""
    if history:
        turns = []
        for turn in history[-REDIS_MAX_HISTORY:]:
            role = "Пользователь" if turn["role"] == "user" else "Ассистент"
            turns.append(f"{role}: {turn['content']}")
        history_text = "\n".join(turns)

    return f"""Ты корпоративный ассистент компании SideWays. Отвечай только на основе имеющейся информации и предоставленного контекста.
Если ответа нет в контексте — скажи об этом прямо.

Контекст:
{joined_context}

{f"История диалога:{chr(10)}{history_text}{chr(10)}" if history_text else ""}
Вопрос: {question}

Ответ:"""