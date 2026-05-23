import json
import re
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_provider import LLMProvider, SearchSource

SYSTEM_PROMPT = """Ты — поисковый ассистент. Отвечай точно и по делу на русском языке.
Используй только предоставленные источники и цитируй их номерами [1], [2] и т.д.
Не выдумывай факты, которых нет в источниках."""


def _format_sources(sources: list[SearchSource]) -> str:
    lines = []
    for s in sources:
        lines.append(f'[{s.index}] {s.domain} — "{s.title}": {s.snippet}')
    return "\n".join(lines)


def _format_history(history: list[tuple[str, str]]) -> str:
    if not history:
        return ""
    parts = []
    for role, text in history[-6:]:
        label = "Пользователь" if role == "user" else "Ассистент"
        parts.append(f"{label}: {text[:1500]}")
    return "\n\nПредыдущий диалог:\n" + "\n".join(parts)


class YandexGPTProvider(LLMProvider):
    COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _model_uri(self) -> str:
        return f"gpt://{self.settings.yandex_folder_id}/yandexgpt-lite/latest"

    def _build_messages(self, query: str, sources: list[SearchSource], history: list[tuple[str, str]]) -> list[dict]:
        user_content = f"""Источники:
{_format_sources(sources)}
{_format_history(history)}

Вопрос: {query}"""
        return [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": user_content},
        ]

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
    ) -> AsyncIterator[str]:
        if not self.settings.yandex_configured:
            mock = (
                "Квантовые компьютеры — это устройства, которые используют квантовые биты (кубиты) "
                "и явления суперпозиции и запутанности для выполнения вычислений [1][2]. "
                "В отличие от классических компьютеров, они потенциально эффективны для отдельных "
                "классов задач, таких как факторизация и моделирование молекул [2]."
            )
            for word in mock.split(" "):
                yield word + " "
            return

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": self._model_uri(),
            "completionOptions": {
                "stream": True,
                "temperature": 0.3,
                "maxTokens": 2000,
            },
            "messages": self._build_messages(query, sources, history),
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self.COMPLETION_URL, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if not chunk or chunk == "[DONE]":
                        continue
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    alts = parsed.get("result", {}).get("alternatives", [])
                    if alts:
                        text = alts[0].get("message", {}).get("text", "")
                        if text:
                            yield text

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        if not self.settings.yandex_configured:
            return [
                "Чем квантовый компьютер отличается от обычного?",
                "Где квантовые компьютеры применяются сейчас?",
                "Кто лидирует в разработке квантовых технологий?",
            ]

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": self._model_uri(),
            "completionOptions": {"stream": False, "temperature": 0.5, "maxTokens": 300},
            "messages": [
                {
                    "role": "system",
                    "text": "Сгенерируй ровно 3 коротких уточняющих вопроса по теме. Ответ — JSON массив строк.",
                },
                {
                    "role": "user",
                    "text": f"Запрос: {query}\n\nОтвет: {answer[:2000]}",
                },
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.COMPLETION_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        text = data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return [str(x) for x in items[:3]]
            except json.JSONDecodeError:
                pass
        return [q.strip() for q in text.split("\n") if q.strip()][:3] or [
            "Расскажи подробнее",
            "Приведи примеры",
            "Какие есть риски?",
        ]
