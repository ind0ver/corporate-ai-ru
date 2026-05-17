import json
import random
import string

import requests
import streamlit as st

from backend.config import MODEL, SYSTEM_PROMPT, BACKEND_URL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_name(length: int = 8) -> str:
    """Генерирует случайное имя из букв и цифр."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


@st.cache_data(ttl=60)
def fetch_available_models() -> list[str]:
    """Запрашивает список моделей у backend. Кешируется на 60 секунд."""
    try:
        r = requests.get(f"{BACKEND_URL}/models", timeout=5)
        r.raise_for_status()
        models = r.json()
        return models if isinstance(models, list) and models else [MODEL]
    except Exception as e:
        st.warning(f"Не удалось получить список моделей: {e}")
        return [MODEL]


def resolve_default_model(model: str, available: list[str]) -> str:
    return model if model in available else available[0]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get_users() -> list[dict]:
    """[{"user_id": ..., "name": ...}, ...] — отсортированы по последней активности."""
    try:
        r = requests.get(f"{BACKEND_URL}/users", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def api_create_user(name: str) -> dict | None:
    try:
        r = requests.post(f"{BACKEND_URL}/users", json={"name": name}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Не удалось создать пользователя: {e}")
        return None


def api_get_sessions(user_id: str) -> list[str]:
    try:
        r = requests.get(f"{BACKEND_URL}/users/{user_id}/sessions", timeout=5)
        r.raise_for_status()
        return [s["session_id"] for s in r.json()]
    except Exception:
        return []


def api_create_session(user_id: str) -> str | None:
    try:
        r = requests.post(f"{BACKEND_URL}/users/{user_id}/sessions", timeout=5)
        r.raise_for_status()
        return r.json()["session_id"]
    except Exception as e:
        st.error(f"Не удалось создать сессию: {e}")
        return None


def api_get_history(session_id: str) -> list[dict]:
    try:
        r = requests.get(f"{BACKEND_URL}/sessions/{session_id}/history", timeout=5)
        r.raise_for_status()
        return r.json().get("history", [])
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

def _bootstrap_first_user() -> None:
    """Вызывается один раз при первом открытии если нет ни одного пользователя."""
    name = random_name()
    user = api_create_user(name)
    if not user:
        return
    session_id = api_create_session(user["user_id"])
    users = api_get_users()

    st.session_state.users_cache = users
    st.session_state.active_user_id = user["user_id"]
    st.session_state.active_user_name = user["name"]
    st.session_state.sessions_cache = [session_id] if session_id else []
    st.session_state.active_session_id = session_id
    st.session_state.chat_history = []


def _restore_last_active() -> None:
    """Восстанавливает последнего активного пользователя и его последнюю сессию."""
    users = api_get_users()
    st.session_state.users_cache = users

    if not users:
        _bootstrap_first_user()
        return

    # get_users возвращает по убыванию активности — первый = последний активный
    user = users[0]
    st.session_state.active_user_id = user["user_id"]
    st.session_state.active_user_name = user["name"]

    sessions = api_get_sessions(user["user_id"])
    st.session_state.sessions_cache = sessions
    st.session_state.active_session_id = sessions[0] if sessions else None
    st.session_state.chat_history = (
        api_get_history(sessions[0]) if sessions else []
    )


def init_session_state() -> None:
    """
    Инициализация при первом запуске вкладки браузера.
    Streamlit вызывает весь скрипт при каждом взаимодействии —
    проверяем 'not in' перед каждым присвоением.
    """
    if "available_models" not in st.session_state:
        st.session_state.available_models = fetch_available_models()

    if "model" not in st.session_state:
        st.session_state.model = resolve_default_model(
            MODEL, st.session_state.available_models
        )

    if "temperature" not in st.session_state:
        st.session_state.temperature = 0.2

    if "system_prompt" not in st.session_state:
        st.session_state.system_prompt = SYSTEM_PROMPT

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "users_cache" not in st.session_state:
        st.session_state.users_cache = []

    if "sessions_cache" not in st.session_state:
        st.session_state.sessions_cache = []

    # active_user_id — единственный флаг "уже инициализировано":
    # если его нет — это первый рендер вкладки, грузим из Redis
    if "active_user_id" not in st.session_state:
        st.session_state.active_user_id = None
        st.session_state.active_user_name = None
        st.session_state.active_session_id = None
        _restore_last_active()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def action_select_user(user_id: str, user_name: str) -> None:
    """Переключиться на пользователя, загрузить его последнюю сессию."""
    st.session_state.active_user_id = user_id
    st.session_state.active_user_name = user_name

    sessions = api_get_sessions(user_id)
    st.session_state.sessions_cache = sessions

    if sessions:
        st.session_state.active_session_id = sessions[0]
        st.session_state.chat_history = api_get_history(sessions[0])
    else:
        st.session_state.active_session_id = None
        st.session_state.chat_history = []


def action_select_session(session_id: str) -> None:
    """Переключиться на другую сессию текущего пользователя."""
    st.session_state.active_session_id = session_id
    st.session_state.chat_history = api_get_history(session_id)


def action_add_user() -> None:
    """Создать пользователя с рандомным именем + сразу новую сессию для него."""
    name = random_name()
    user = api_create_user(name)
    if not user:
        return

    session_id = api_create_session(user["user_id"])

    # Обновляем кеш пользователей
    st.session_state.users_cache = api_get_users()

    # Переключаемся на нового пользователя
    st.session_state.active_user_id = user["user_id"]
    st.session_state.active_user_name = user["name"]
    st.session_state.sessions_cache = [session_id] if session_id else []
    st.session_state.active_session_id = session_id
    st.session_state.chat_history = []


def action_add_session() -> None:
    """Создать новую сессию для текущего пользователя и переключиться на неё."""
    user_id = st.session_state.active_user_id
    if not user_id:
        return
    session_id = api_create_session(user_id)
    if session_id:
        st.session_state.sessions_cache = api_get_sessions(user_id)
        st.session_state.active_session_id = session_id
        st.session_state.chat_history = []

    if "session_select" in st.session_state:
        del st.session_state["session_select"]


def reset_chat() -> None:
    """Очищает историю в UI (не удаляет из Redis)."""
    st.session_state.chat_history = []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar() -> None:
    """Отрисовывает боковую панель с настройками."""
    with st.sidebar:
        st.title("⚙️ Настройки")

        # ── Модель ────────────────────────────────────────────────────────
        available = st.session_state.available_models
        current_index = (
            available.index(st.session_state.model)
            if st.session_state.model in available
            else 0
        )
        st.session_state.model = st.selectbox(
            "Модель",
            available,
            index=current_index,
            key="model_select",
        )

        # ── Temperature ───────────────────────────────────────────────────
        st.session_state.temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.temperature,
            step=0.05,
            key="temperature_slider",
            help="0 — детерминированный ответ, 1 — максимальная случайность",
        )

        # ── Очистить чат ──────────────────────────────────────────────────
        if st.button("🗑️ Очистить чат", use_container_width=True):
            reset_chat()
            st.rerun()

        # ── Пользователь ──────────────────────────────────────────────────
        st.divider()

        users = st.session_state.users_cache
        user_ids   = [u["user_id"] for u in users]
        user_names = [u["name"]    for u in users]

        active_uid = st.session_state.active_user_id
        user_index = user_ids.index(active_uid) if active_uid in user_ids else 0

        selected_user_name = st.selectbox(
            "Пользователь",
            options=user_names,
            index=user_index,
            key="user_select",
        )

        if st.button("＋ Новый пользователь", key="add_user_btn", use_container_width=True):
            action_add_user()
            st.rerun()

        # Реагируем на смену пользователя через dropdown
        if selected_user_name and user_names:
            selected_uid = user_ids[user_names.index(selected_user_name)]
            if selected_uid != st.session_state.active_user_id:
                action_select_user(selected_uid, selected_user_name)
                st.rerun()

        # ── Сессия ────────────────────────────────────────────────────────
        
        sessions = st.session_state.sessions_cache
        active_sid = st.session_state.active_session_id

        session_labels = [s for s in sessions]

        selected_session_label = st.selectbox(
            "Сессия",
            options=session_labels if session_labels else ["—"],
            index=sessions.index(active_sid) if active_sid in sessions else 0,
            key="session_select",
            disabled=not sessions,
        )

        if st.button("＋ Новая сессия", key="add_session_btn", use_container_width=True):
            action_add_session()
            st.rerun()

        # Реагируем на смену сессии через dropdown
        if sessions and selected_session_label != "—":
            selected_sid = sessions[session_labels.index(selected_session_label)]
            if selected_sid != st.session_state.active_session_id:
                action_select_session(selected_sid)
                st.rerun()

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def render_chat_history() -> None:
    """Отрисовывает историю сообщений."""
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def stream_response(prompt: str) -> str:
    """Стримит ответ из backend, возвращает полный текст."""
    payload = {
        "user_id":      st.session_state.active_user_id,
        "session_id":   st.session_state.active_session_id,
        "message":      prompt,
        "model":        st.session_state.model,
        "temperature":  st.session_state.temperature,
        "system_prompt": st.session_state.system_prompt,
    }

    full_response = ""
    message_placeholder = st.empty()

    with requests.post(
        f"{BACKEND_URL}/chat/stream",
        json=payload,
        stream=True,
        timeout=120,
        headers={"Accept": "text/event-stream"},
    ) as response:
        response.raise_for_status()

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if raw_line == "data: [DONE]":
                break
            if not raw_line.startswith("data: "):
                continue
            try:
                data = json.loads(raw_line[6:])
            except json.JSONDecodeError:
                continue
            if "error" in data:
                raise RuntimeError(data["error"])
            token = data.get("token", "")
            full_response += token
            message_placeholder.markdown(full_response + "▌")

    message_placeholder.markdown(full_response)
    return full_response


def handle_user_input(prompt: str) -> None:
    """Обрабатывает сообщение пользователя: добавляет в историю и получает ответ."""
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            answer = stream_response(prompt)
        except Exception as e:
            answer = f"❌ Ошибка при обращении к серверу: {e}"
            st.markdown(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Корпоративный AI",
        page_icon="💼",
        layout="centered",
    )

    init_session_state()
    render_sidebar()

    st.title("💼 Корпоративный AI")

    render_chat_history()

    if prompt := st.chat_input("Введите вопрос…"):
        handle_user_input(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
