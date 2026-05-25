import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]

SYSTEM_PROMPT_SEARCH = """Ты — поисковый ассистент Glosix. Отвечай точно и по делу на русском языке.
Используй только предоставленные источники и цитируй их номерами [1], [2] и т.д.
Не выдумывай факты, которых нет в источниках."""

SYSTEM_PROMPT_DIRECT = """Ты — ассистент Glosix. Отвечай на русском по делу, используя контекст диалога.
Если в контексте есть ранее найденные источники — можешь ссылаться на [1], [2].
Не выдумывай актуальные факты (курсы валют, новости, цены) — предложи уточнить или выполнить поиск."""


def _format_sources(sources: list[SearchSource]) -> str:
    if not sources:
        return "Нет новых источников (опирайся на диалог и ранее найденные данные)."
    lines = []
    for s in sources:
        lines.append(f'[{s.index}] {s.domain} — "{s.title}": {s.snippet}')
    return "\n".join(lines)


def _format_history(history: list[tuple[str, str]], max_turns: int = 6) -> str:
    if not history:
        return ""
    parts = []
    for role, text in history[-max_turns:]:
        label = "Пользователь" if role == "user" else "Ассистент"
        parts.append(f"{label}: {text[:1500]}")
    return "\n\nПредыдущий диалог:\n" + "\n".join(parts)


class YandexGPTProvider(LLMProvider):
    COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _model_uri(self, model: AnswerModel = "lite") -> str:
        return self.settings.yandex_model_uri(model)

    def _build_messages_search(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        user_content = f"""Источники:
{_format_sources(sources)}
{_format_history(history)}{extra}

Вопрос: {query}"""
        return [
            {"role": "system", "text": SYSTEM_PROMPT_SEARCH},
            {"role": "user", "text": user_content},
        ]

    def _build_messages_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        user_content = f"""{_format_history(history)}{extra}

Вопрос: {query}"""
        return [
            {"role": "system", "text": SYSTEM_PROMPT_DIRECT},
            {"role": "user", "text": user_content},
        ]

    async def complete_text(
        self,
        messages: list[dict],
        model: AnswerModel = "lite",
        max_tokens: int = 300,
        temperature: float = 0.2,
    ) -> str:
        if not self.settings.yandex_configured:
            return '{"needs_search": true, "search_query": "mock", "answer_model": "lite", "reason": "mock"}'

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": self._model_uri(model),
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": max_tokens,
            },
            "messages": messages,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.COMPLETION_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("YandexGPT HTTP %s: %s", e.response.status_code, e.response.text[:500])
            raise YandexServiceError("gpt", f"YandexGPT недоступен (HTTP {e.response.status_code})", e.response.status_code) from e
        except httpx.HTTPError as e:
            logger.exception("YandexGPT request failed")
            raise YandexServiceError("gpt", "YandexGPT недоступен (сеть)") from e
        return data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")

    async def stream_answer(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.settings.yandex_configured:
            mock = (
                "Квантовые компьютеры используют кубиты и суперпозицию [1][2]. "
                "Они перспективны для отдельных задач [2]."
            )
            for word in mock.split(" "):
                yield word + " "
            return

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        max_tokens = 3000 if model == "pro" else 2000
        payload = {
            "modelUri": self._model_uri(model),
            "completionOptions": {
                "stream": True,
                "temperature": 0.3,
                "maxTokens": max_tokens,
            },
            "messages": self._build_messages_search(query, sources, history, prior_sources_block),
        }

        async for chunk in self._stream_completion(payload, headers):
            yield chunk

    async def stream_answer_direct(
        self,
        query: str,
        history: list[tuple[str, str]],
        model: AnswerModel = "lite",
        prior_sources_block: str = "",
    ) -> AsyncIterator[str]:
        if not self.settings.yandex_configured:
            for word in "Отвечаю по контексту диалога без нового поиска.".split(" "):
                yield word + " "
            return

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        max_tokens = 2500 if model == "pro" else 1500
        payload = {
            "modelUri": self._model_uri(model),
            "completionOptions": {
                "stream": True,
                "temperature": 0.4,
                "maxTokens": max_tokens,
            },
            "messages": self._build_messages_direct(query, history, prior_sources_block),
        }

        async for chunk in self._stream_completion(payload, headers):
            yield chunk

    async def _stream_completion(self, payload: dict, headers: dict) -> AsyncIterator[str]:
        prev_len = 0
        try:
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
                            if text and len(text) > prev_len:
                                yield text[prev_len:]
                                prev_len = len(text)
        except httpx.HTTPStatusError as e:
            logger.error("YandexGPT stream HTTP %s: %s", e.response.status_code, e.response.text[:500])
            raise YandexServiceError("gpt", f"YandexGPT недоступен (HTTP {e.response.status_code})", e.response.status_code) from e
        except httpx.HTTPError as e:
            logger.exception("YandexGPT stream failed")
            raise YandexServiceError("gpt", "YandexGPT недоступен (сеть)") from e

    async def generate_follow_ups(self, query: str, answer: str) -> list[str]:
        if not self.settings.yandex_configured:
            return [
                "Расскажи подробнее",
                "Приведи примеры",
                "Какие есть риски?",
            ]

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": self._model_uri("lite"),
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

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.COMPLETION_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Follow-ups YandexGPT HTTP %s", e.response.status_code)
            return [
                "Расскажи подробнее",
                "Приведи примеры",
                "Какие есть риски?",
            ]
        except httpx.HTTPError:
            logger.exception("Follow-ups request failed")
            return [
                "Расскажи подробнее",
                "Приведи примеры",
                "Какие есть риски?",
            ]

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
