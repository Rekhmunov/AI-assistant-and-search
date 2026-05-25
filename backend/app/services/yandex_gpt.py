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

SYSTEM_PROMPT_SEARCH = """Ты — экспертный поисковый ассистент Glosix (уровень качества как Perplexity). Язык ответа: русский.

Правила содержания:
- Опирайся ТОЛЬКО на предоставленные источники; цитируй факты номерами [1], [2] и т.д.
- Не выдумывай шаги, URL, роли IAM и параметры API, которых нет в источниках.
- Если в источниках мало деталей — задай один конкретный уточняющий вопрос (город, дата, модель), а не отсылай «посмотрите на сайте».
- Не отправляй пользователя на внешние сервисы вместо ответа по [1], [2].

Структура ответа (для инструкций и «как настроить»):
1. Короткое вступление — 1–2 предложения.
2. Разделы: заголовок отдельной строкой БЕЗ символов # и без звёздочек (просто текст, например: «Подготовка»).
3. Шаги — нумерованный список: 1. 2. 3. Подпункты — строки с тире «— ».
4. Приоритет официальных источников при цитировании [1], [2].
5. В конце — один уточняющий вопрос, если уместно.

Форматирование (строго):
- Только обычный текст и переносы строк. ЗАПРЕЩЕНО: #, ##, ###, **, __, `, markdown-заголовки.
- Не используй жирный и курсив через звёздочки — выделяй смысл формулировками, не разметкой.
- Абзацы отделяй пустой строкой."""

SYSTEM_PROMPT_DIRECT = """Ты — ассистент Glosix. Отвечай на русском по делу, используя контекст диалога.
Если в контексте есть ранее найденные источники — можешь ссылаться на [1], [2].
Не выдумывай актуальные факты (курсы валют, новости, цены) — предложи уточнить или выполнить поиск.
Формат: только простой текст с абзацами, без markdown (#, **, `)."""

SYSTEM_PROMPT_DOCUMENT = """Ты — ассистент Glosix. Пользователь прикрепил файл(ы); их текст в запросе в блоках «--- Документ: имя ---».

Правила:
- Анализируй в первую очередь содержимое этих блоков, а не «источники из интернета».
- Для 1CClientBankExchange / обмен с банком: опиши структуру, секции, реквизиты, суммы, ошибки или несоответствия, если видны в тексте.
- Если текст нечитаем, пустой или обрезан — скажи прямо и что нужно (фрагмент, другая кодировка, экспорт заново).
- Не отсылай пользователя к веб-поиску вместо разбора файла.
- Формат: простой текст с абзацами, без markdown (#, **, `)."""


def _query_has_document_block(query: str) -> bool:
    return "--- Документ:" in query


def _format_sources(sources: list[SearchSource], max_snippet: int = 900) -> str:
    if not sources:
        return "Нет новых источников (опирайся на диалог и ранее найденные данные)."
    lines = []
    for s in sources:
        snippet = (s.snippet or "")[:max_snippet]
        lines.append(f'[{s.index}] {s.domain} — "{s.title}"\nURL: {s.url}\n{snippet}')
    return "\n\n".join(lines)


def _text_from_completion_json(data: dict) -> str:
    alts = data.get("result", {}).get("alternatives", [])
    if not alts:
        return ""
    return alts[0].get("message", {}).get("text", "") or ""


def _parse_completion_stream_line(line: str) -> str | None:
    raw = line.strip()
    if not raw or raw == "[DONE]":
        return None
    if raw.startswith("data:"):
        raw = raw[5:].strip()
    if not raw.startswith("{"):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _text_from_completion_json(parsed) or None


async def _yield_text_paced(text: str) -> AsyncIterator[str]:
    if not text:
        return
    parts = re.split(r"(?<=\s)", text)
    for part in parts:
        if part:
            yield part


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
        system = (
            SYSTEM_PROMPT_DOCUMENT
            if _query_has_document_block(query)
            else SYSTEM_PROMPT_DIRECT
        )
        return [
            {"role": "system", "text": system},
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
        return _text_from_completion_json(data)

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
        max_tokens = 4500 if model == "pro" else 2800
        payload = {
            "modelUri": self._model_uri(model),
            "completionOptions": {
                "stream": True,
                "temperature": 0.35 if model == "pro" else 0.3,
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
        stream_payload = {
            **payload,
            "completionOptions": {**payload["completionOptions"], "stream": True},
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", self.COMPLETION_URL, headers=headers, json=stream_payload
                ) as response:
                    response.raise_for_status()
                    buffer = ""
                    async for raw_chunk in response.aiter_bytes():
                        buffer += raw_chunk.decode("utf-8", errors="replace")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            full_text = _parse_completion_stream_line(line)
                            if full_text and len(full_text) > prev_len:
                                yield full_text[prev_len:]
                                prev_len = len(full_text)
                    if buffer.strip():
                        full_text = _parse_completion_stream_line(buffer)
                        if full_text and len(full_text) > prev_len:
                            yield full_text[prev_len:]
                            prev_len = len(full_text)
                        elif buffer.strip().startswith("{"):
                            try:
                                parsed = json.loads(buffer.strip())
                                full_text = _text_from_completion_json(parsed)
                                if full_text and len(full_text) > prev_len:
                                    yield full_text[prev_len:]
                                    prev_len = len(full_text)
                            except json.JSONDecodeError:
                                pass
        except httpx.HTTPStatusError as e:
            logger.error("YandexGPT stream HTTP %s: %s", e.response.status_code, e.response.text[:500])
            raise YandexServiceError("gpt", f"YandexGPT недоступен (HTTP {e.response.status_code})", e.response.status_code) from e
        except httpx.HTTPError as e:
            logger.exception("YandexGPT stream failed")
            raise YandexServiceError("gpt", "YandexGPT недоступен (сеть)") from e

        if prev_len > 0:
            return

        logger.info("YandexGPT stream returned no text, using non-streaming fallback")
        fallback_payload = {
            **payload,
            "completionOptions": {**payload["completionOptions"], "stream": False},
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.COMPLETION_URL, headers=headers, json=fallback_payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error("YandexGPT fallback HTTP %s: %s", e.response.status_code, e.response.text[:500])
            raise YandexServiceError("gpt", f"YandexGPT недоступен (HTTP {e.response.status_code})", e.response.status_code) from e
        except httpx.HTTPError as e:
            logger.exception("YandexGPT fallback request failed")
            raise YandexServiceError("gpt", "YandexGPT недоступен (сеть)") from e

        text = _text_from_completion_json(data)
        if not text:
            logger.warning("YandexGPT fallback returned empty text")
            return
        async for part in _yield_text_paced(text):
            yield part

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

        text = _text_from_completion_json(data)
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
