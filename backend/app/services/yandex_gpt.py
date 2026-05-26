import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from app.core.config import Settings, get_settings
from app.services.llm_provider import LLMProvider, SearchSource
from app.services.search_query import is_meta_assistant_query
from app.services.answer_guard import strict_answer_addon
from app.services.facts.format import format_fact_pack_for_prompt
from app.services.facts.models import FactPack
from app.services.yandex_errors import YandexServiceError

logger = logging.getLogger(__name__)

AnswerModel = Literal["lite", "pro"]

SYSTEM_PROMPT_SEARCH = """Ты — Glosix: умный собеседник-эксперт. Язык: русский.

Твоя модель работы — как у человека, который разбирается в теме:
1) понять вопрос и контекст диалога;
2) опереться на найденные материалы [1], [2] и выдержки со страниц;
3) выдать связный, систематизированный ответ своими словами — не пересказ ссылок.

Содержание:
- Сразу отвечай по сути; факты, цифры, даты, имена — из источников с пометкой [n].
- Не выдумывай то, чего нет в источниках и истории.
- Если в вопросе «--- Документ:» — сначала файл; веб-источники для внешних фактов.
- Если просят сократить/перефразировать — из последнего ответа ассистента в истории.

Тон (обязательно):
- Ты уже получил результаты веб-поиска ниже — отвечай сразу по теме, как эксперт. Поиск для пользователя уже сделан.
- НИКОГДА не пиши: «к сожалению», «у меня нет знаний/специализации», «я не эксперт», «не разбираюсь в…», «давайте попробуем найти», «я могу найти/использовать ресурсы».
- Не описывай процесс («давайте поищем», «обращусь к сайтам») — только выводы из [1], [2].
- Не вставляй голые https://… вместо ответа; URL только внутри смысла, если нужен домен источника.

ЗАПРЕЩЕНО (шаблоны и отговорки):
- «перейдите на сайт», списки URL/порталов вместо ответа;
- «я только поисковый ассистент», «не умею программировать», «обратитесь к специалисту» без разбора;
- пустые фразы «в интернете можно найти…» без конкретики из источников.
- Если данных мало — что удалось выяснить из [n] (1–2 факта), без отказа от темы; один уточняющий вопрос в конце, не «сделайте поиск сами».
- Курс валют: сразу цифры (официальный ЦБ и при необходимости биржевой), без списка banki.ru / cbr.ru «где посмотреть».
- Блок «Проверенные факты»: цифры и даты только оттуда; источники [n] для цитат.

Структура ответа:
1. Суть — 1–3 предложения, прямой ответ.
2. Детали — логические блоки: заголовок отдельной строкой (без # и **), абзацы, при необходимости нумерация 1. 2. 3.
3. Для how-to и программ (похудение, тренировки, «курс»): пошаговый план — недели/дни, конкретные действия, цифры (ккал, повторения, минуты) только из [n]. Если пользователь просит «подробный» / «план» — развёрнутый ответ, не общие советы в 5 предложениях.
4. Уточняющий вопрос в конце ответа — только если без параметра (город, диагноз, цель веса) нельзя составить план; не спрашивай очевидное после уже данного плана.

Формат: только текст и переносы строк; без markdown (#, **, `)."""

SYSTEM_PROMPT_META = """Ты — Glosix: умный ассистент с доступом к веб-поиску.

На вопросы о себе: ты анализируешь запрос, ищешь актуальные данные в сети и отвечаешь связным текстом с цитатами [n], а не списком сайтов.
Помогаешь с кодом и IT через поиск документации и разбор задач; с файлами, инструкциями, сравнениями.
Не называй себя «только поисковиком» и не отказывай шаблоном. Формат: простой текст, без markdown."""

SYSTEM_PROMPT_DIRECT = """Ты — Glosix, умный собеседник. Отвечай по-русски по делу, из контекста диалога.
Если есть источники [1], [2] — опирайся на них.
Не пиши «нет знаний», «к сожалению не могу», «давайте поищем» — сразу по сути.
Формат: простой текст, без markdown."""

SYSTEM_PROMPT_DOCUMENT = """Ты — ассистент Glosix. Пользователь прикрепил файл(ы); их текст в запросе в блоках «--- Документ: имя ---».

Правила:
- Анализируй в первую очередь содержимое этих блоков, а не «источники из интернета».
- Для 1CClientBankExchange / обмен с банком: опиши структуру, секции, реквизиты, суммы, ошибки или несоответствия, если видны в тексте.
- Если текст нечитаем, пустой или обрезан — скажи прямо и что нужно (фрагмент, другая кодировка, экспорт заново).
- Не отсылай пользователя к веб-поиску вместо разбора файла.
- Формат: простой текст с абзацами, без markdown (#, **, `)."""


def _query_has_document_block(query: str) -> bool:
    return "--- Документ:" in query


def _format_sources(sources: list[SearchSource], max_snippet: int = 1400) -> str:
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

    def _build_messages_from_fact_pack(
        self,
        query: str,
        sources: list[SearchSource],
        fact_pack: FactPack,
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
    ) -> list[dict]:
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = (
                f"\n\nПодсказка: в выдаче может не хватать данных. "
                f"В конце ответа задай уточнение: {hint_clarify}"
            )
        strict_block = strict_answer_addon() if strict_facts else ""
        facts_block = format_fact_pack_for_prompt(fact_pack, sources)
        user_content = f"""{facts_block}
{_format_history(history)}{extra}{clarify_block}{strict_block}

Вопрос: {query}"""
        return [
            {"role": "system", "text": SYSTEM_PROMPT_SEARCH},
            {"role": "user", "text": user_content},
        ]

    def _build_messages_search(
        self,
        query: str,
        sources: list[SearchSource],
        history: list[tuple[str, str]],
        prior_sources_block: str = "",
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
    ) -> list[dict]:
        if fact_pack is not None:
            return self._build_messages_from_fact_pack(
                query,
                sources,
                fact_pack,
                history,
                prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
            )
        extra = f"\n\n{prior_sources_block}" if prior_sources_block else ""
        clarify_block = ""
        if hint_clarify:
            clarify_block = f"\n\nПодсказка: в выдаче может не хватать данных. В конце ответа задай уточнение: {hint_clarify}"
        strict_block = strict_answer_addon() if strict_facts else ""
        user_content = f"""Источники:
{_format_sources(sources)}
{_format_history(history)}{extra}{clarify_block}{strict_block}

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
        if _query_has_document_block(query):
            system = SYSTEM_PROMPT_DOCUMENT
        elif is_meta_assistant_query(query):
            system = SYSTEM_PROMPT_META
        else:
            system = SYSTEM_PROMPT_DIRECT
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
        *,
        hint_clarify: str | None = None,
        strict_facts: bool = False,
        fact_pack: FactPack | None = None,
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
            "messages": self._build_messages_search(
                query,
                sources,
                history,
                prior_sources_block,
                hint_clarify=hint_clarify,
                strict_facts=strict_facts,
                fact_pack=fact_pack,
            ),
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
                "Пошаговый план на месяц",
                "Примеры меню и калорий",
                "Типичные ошибки при похудении",
            ]

        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "modelUri": self._model_uri("lite"),
            "completionOptions": {"stream": False, "temperature": 0.4, "maxTokens": 320},
            "messages": [
                {
                    "role": "system",
                    "text": (
                        "Сгенерируй ровно 3 короткие фразы — заголовки для продолжения темы "
                        "(следующий запрос пользователя). Утвердительные формулировки, без знака «?», "
                        "не вопросы к пользователю. 4–12 слов. Примеры: «План питания на 1500 ккал», "
                        "«Тренировки на 4 недели для начинающих». Ответ — только JSON-массив строк."
                    ),
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
            return _default_follow_up_suggestions(query)
        except httpx.HTTPError:
            logger.exception("Follow-ups request failed")
            return _default_follow_up_suggestions(query)

        text = _text_from_completion_json(data)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group())
                if isinstance(items, list):
                    return _normalize_follow_up_suggestions([str(x) for x in items[:3]])
            except json.JSONDecodeError:
                pass
        lines = [q.strip() for q in text.split("\n") if q.strip()][:3]
        return _normalize_follow_up_suggestions(lines) or _default_follow_up_suggestions(query)


def _normalize_follow_up_suggestions(items: list[str]) -> list[str]:
    out: list[str] = []
    for raw in items:
        s = raw.strip().strip("-•").strip()
        if s.endswith("?"):
            s = s[:-1].strip()
        if not s or "?" in s:
            continue
        if re.match(r"^(какие|какой|какая|как|есть ли|уточните)\b", s, re.I):
            continue
        out.append(s[:120])
        if len(out) >= 3:
            break
    return out


def _default_follow_up_suggestions(query: str) -> list[str]:
    q = query.lower()
    if "похуд" in q or "курс" in q:
        return [
            "Пошаговый план похудения на 4 недели",
            "Меню и калорийность на день",
            "Силовые и кардио: схема на неделю",
        ]
    return [
        "Подробный разбор по шагам",
        "Примеры и цифры по теме",
        "Сравнение основных подходов",
    ]
