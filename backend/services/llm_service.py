import json
import httpx
import requests
from backend.config import LLM_API_URL
from typing import List


async def generate_stream(
    prompt: str,
    model: str,
    system_prompt: str,
    temperature: float
):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperature,
        "stream": True
    }

    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST",
            f"{LLM_API_URL}/v1/chat/completions",
            json=payload
        ) as response:

            async for line in response.aiter_lines():

                if not line:
                    continue

                if not line.startswith("data: "):
                    continue

                data = line[6:]

                if data == "[DONE]":
                    break

                chunk = json.loads(data)

                delta = chunk["choices"][0]["delta"]

                token = delta.get("content")

                if token:
                    yield token


def get_available_models() -> List[str]:
    try:
        response = requests.get(f"{LLM_API_URL}/v1/models", timeout=5)
        response.raise_for_status()
        data = response.json()

        # Извлекаем имена моделей из поля "id" каждой записи в списке "data"
        models_data = data.get("data", [])
        return [model["id"] for model in models_data]

    except requests.exceptions.ConnectionError:
        print("OpenAI‑compatible API недоступна")
        return []
    except Exception as e:
        print(f"Ошибка получения моделей: {e}")
        return []