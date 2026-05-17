# CorporateAI — корпоративный AI‑ассистент
RAG-cервис для консультации с корпоративной базой знаний с параллельной обработкой запросов на базе FastAPI, Qdrant, Redis и vLLM для многопользовательского чата с локальной LLM и placeholder frontend на Streamlit.

## Ключевые возможности

* **Многопользовательский сервис:** подходит для использования несколькими пользователями одновременно.
* **Потоковая передача:** стриминг ответов от AI в реальном времени.
* **Локальное развёртывание:** полный контроль над данными и моделями.

## Стек

* **Инференс LLM:** OpenAI compatible endpoint (рекомендуется vLLM для обработки параллельных запросов).
* **Векторная БД:** Qdrant.
* **Кэш и управление сессиями:** Redis.
* **Бэкенд‑интеграция:** FastAPI.
* **Фронтенд:** Streamlit.

## Установка и запуск
1. Redis and Qdrant must be installed and running (i.e. Docker) with ports configured in backend/config.py.
Have a vLLM server running with the port available and configured.

2. Make sure to activate the virtual environment:
```bash
.venv\Scripts\activate
```
and have dependencies installed with 
```bash
pip install -r requirements.txt
```


3. Load pdf documents into /docs folder.

4. Run
```bash
python -m rag.ingest
```
to ingest files and create a qdrant collection (vector DB).

5. Run and keep running the backend server
```bash
uvicorn backend.main:app
```

6. In a separate terminal, run the frontend with
```bash
streamlit run frontend/app.py
```
This will open the UI in the browser.

7. Talk to the LLM about the PDF documents in the /docs folder.

## Использование с Docker
Рекомендуемые контейнеры:
 - qdrant/qdrant:latest
 - redis:latest
 - vllm/vllm-openai:latest
