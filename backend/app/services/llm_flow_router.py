"""Маршрутизация запроса через LLM: выбор потока сервиса без длинных regex-правил."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from app.models.user import Plan
from app.services.doc_gen_context import refers_to_prior_answer
from app.services.doc_gen_routing import wants_document_generation
from app.services.providers.factory import ChatLLM
from app.services.search_query import normalize_user_query
from app.services.thread_context import ThreadContext, format_history_compact

logger = logging.getLogger(__name__)

ServiceFlow = Literal[
    "search_rag",
    "chat",
    "image_generate",
    "export_chat_document",
    "compress_pdf",
    "convert_pdf",
]

_FLOW_JSON_RE = re.compile(r"\{[\s\S]*\}")


@dataclass
class LlmFlowDecision:
    flow: ServiceFlow
    needs_search: bool
    answer_model: Literal["lite", "pro"]
    reason: str
    force_yandex: bool = False


_ROUTER_SYSTEM = """Ты маршрутизатор запросов в Glosix (умный ассистент с веб-поиском и файлами).

Верни ТОЛЬКО JSON без markdown:
{
  "flow": "search_rag" | "chat" | "image_generate" | "export_chat_document",
  "needs_search": true/false,
  "answer_model": "lite" | "pro",
  "reason": "кратко по-русски",
  "force_yandex": true/false
}

answer_model = "pro" — запрос требует глубокого анализа или синтеза нескольких источников:
- Сравнение с оценкой: «сравни X и Y», «что лучше A или B», «чем отличается» (с просьбой оценить)
- Аналитика: «проанализируй», «оцени плюсы и минусы», «разбери по критериям»
- Причины и связи: «почему X влияет на Y», «каковы причины», «как это связано с»
- Выбор и стратегия: «как выбрать», «что учесть при», «какие риски», «стоит ли»
- Обзоры: «лучшие решения для X», «обзор рынка Y», «топ инструментов»
- Сложные механизмы: «как устроена система X», «как работает процесс», «как организовать»

answer_model = "lite" — всё остальное:
- Простые факты: «кто такой X», «цена Y», «где находится», «когда основан»
- Новости и текущие события (их обрабатывает Яндекс через force_yandex — здесь lite)
- Краткие определения: «что такое X», «расшифруй аббревиатуру»
- Запросы с одним конкретным ответом

ВАЖНО: force_yandex оценивай ТОЛЬКО по текущему запросу пользователя, не по истории треда.
История треда нужна лишь чтобы понять референции («это», «они», «там»), но не для оценки свежести.

force_yandex = true когда ТЕКУЩИЙ запрос подразумевает актуальную/недавнюю информацию,
даже без слов «новости», «сегодня», «свежие»:
- Конкретные происшествия и события: «пожар Садовод», «авария на МКАД», «взрыв в метро» —
  пользователь хочет знать про недавнее событие, не историческое
- Текущее состояние: «что с Газпромом», «Навальный сейчас», «ситуация на границе»
- Действия живых людей и организаций: «что сказал Путин», «Греф объявил», «ЦБ поднял ставку»
- Запросы о ценах, курсах, погоде, расписании — всё что меняется
- ЯВНЫЕ слова: новости, сегодня, вчера, сейчас, только что, последние, свежие, актуально
- ИСКЛЮЧЕНИЕ: если запрос содержит «как подготовиться», «что делать», «рекомендации», «советы» —
  это аналитика, force_yandex = false даже при наличии даты или события

force_yandex = false:
- Исторические события с указанием года или периода: «пожар 1812», «блокада Ленинграда»
- Вечные знания: физика, математика, рецепты, объяснения понятий
- Создание текста, кода, документов
- Вопросы о будущих датах с аналитикой или подготовкой: «что будет с X с 01.09», «как подготовиться
  к изменениям», «что изменится в следующем году», «как адаптироваться» — это прогноз/аналитика,
  не свежая новость
- Запросы «как подготовиться», «что делать», «рекомендации», «советы» — даже если есть дата
- Любые запросы где не нужна свежесть данных

Возможности сервиса:
- search_rag — вопросы о мире, фактах, событиях, людях, продуктах, технологиях, ценах, погоде, новостях. ВСЕГДА needs_search=true.
- chat — создание нового текста: оферты, договоры, заявления, инструкции, объяснения, планы, код. Также: программирование, настройка ПО/конфигов, отладка кода, архитектура, алгоритмы, IT-задачи. needs_search=false.
- image_generate — пользователь просит нарисовать/сгенерировать изображение, картинку, логотип.
- export_chat_document — оформить УЖЕ написанный в переписке текст (ответ выше, текст выше, преобразуй в markdown). Не переписывать содержание.
- compress_pdf — пользователь ЯВНО просит сжать конкретный PDF-файл (прикреплён или упомянут). НЕ использовать если это вопрос о возможностях («умеешь ли», «можешь ли», «что умеешь»).
- convert_pdf — пользователь ЯВНО просит конвертировать конкретный PDF в JPG. НЕ использовать если это вопрос о возможностях.

ВАЖНО — вопросы о возможностях сервиса → chat:
- «ты умеешь X», «можешь ли ты X», «что ты умеешь», «умеешь сжимать», «умеешь конвертировать»
- «ты можешь сделать X», «умеешь делать X», «поддерживаешь X»
- Любой вопрос в форме «ты умеешь/можешь» без прикреплённого файла → chat
  LLM объяснит что умеет и как пользоваться.

ПРАВИЛА МАРШРУТИЗАЦИИ:

Код и программирование → chat, needs_search=false:
- «напиши функцию/класс/скрипт», «как написать код», «реализуй алгоритм»
- «отладь код», «найди ошибку в коде», «объясни этот код»
- «как настроить [nginx/docker/python/git/ssh/env/конфиг]», «настройка окружения»
- «как установить и настроить», «пошаговая настройка», «сделай по шагам»
- «напиши SQL-запрос», «составь regex», «как работает [синтаксис языка]»
- Вопросы про синтаксис, паттерны, архитектуру, алгоритмы — chat, needs_search=false.
- ИСКЛЮЧЕНИЕ: «какая последняя версия X», «changelog X», «что нового в X» → search_rag.

Факты о мире → search_rag, needs_search=true:
- «кто», «что», «где», «когда», «цена», «погода», «новости», «события»
- «чем отличается [продукт A] от [продукт B]», «какой лучший»
- Вопросы о конкретных людях, компаниях, ценах, актуальных данных.

Создание документов → chat, needs_search=true (если нужны примеры):
- «напиши оферту», «создай договор», «сделай заявление».

Экспорт → export_chat_document, needs_search=false:
- «сгенерируй текст выше в документ», «оформи ответ выше», «экспортируй ответ».
- Только если в контексте треда есть предыдущий ответ для экспорта.

Вложения → search_rag, needs_search=true:
- Если в запросе есть [К сообщению прикреплены файлы/фото] — всегда search_rag.

- При сомнении между code/config и фактом — chat, needs_search=false.
- Если flow=search_rag — needs_search ВСЕГДА true.
"""


def _parse_flow_response(raw: str) -> LlmFlowDecision | None:
    text = (raw or "").strip()
    match = _FLOW_JSON_RE.search(text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    flow = str(data.get("flow") or "").strip()
    # legacy: document_file → chat
    if flow == "document_file":
        flow = "chat"
    if flow not in (
        "search_rag",
        "chat",
        "image_generate",
        "export_chat_document",
        "compress_pdf",
        "convert_pdf",
    ):
        return None
    needs_search = bool(data.get("needs_search"))
    model = str(data.get("answer_model") or "lite").strip()
    if model not in ("lite", "pro"):
        model = "lite"
    reason = str(data.get("reason") or "llm_router")[:200]
    force_yandex = bool(data.get("force_yandex", False))
    return LlmFlowDecision(
        flow=flow,  # type: ignore[arg-type]
        needs_search=needs_search,
        answer_model=model,  # type: ignore[arg-type]
        reason=reason,
        force_yandex=force_yandex,
    )


def _normalize_flow(
    query: str,
    decision: LlmFlowDecision,
    user_plan: Plan,
    *,
    has_thread_history: bool,
) -> LlmFlowDecision:
    # Единственная техническая корректировка:
    # search_rag + needs_search=false логически противоречиво.
    if decision.flow == "search_rag" and not decision.needs_search:
        decision.needs_search = True
    return decision


async def resolve_service_flow(
    llm: ChatLLM,
    query: str,
    ctx: ThreadContext,
    *,
    has_attachments: bool,
    user_plan: Plan,
) -> LlmFlowDecision:
    """LLM выбирает поток; при ошибке — безопасный search_rag."""
    q = normalize_user_query(query)

    history = format_history_compact(ctx.history, max_turns=3, max_chars=400)
    user_block = f"Запрос пользователя:\n{q}"
    if has_attachments:
        user_block += "\n[К сообщению прикреплены файлы/фото]"
    if history:
        user_block += f"\n\nКонтекст треда:\n{history}"
    if ctx.is_continuation:
        user_block += "\n(есть предыдущие сообщения в треде)"

    messages = [
        {"role": "system", "text": _ROUTER_SYSTEM},
        {"role": "user", "text": user_block},
    ]
    try:
        raw = await llm.complete_text(
            messages,
            model="lite",
            max_tokens=256,
            temperature=0.0,
        )
        parsed = _parse_flow_response(raw)
        logger.warning(
            "FLOW_ROUTER raw=%s parsed_flow=%s parsed_needs_search=%s",
            (raw or "")[:200],
            parsed.flow if parsed else None,
            parsed.needs_search if parsed else None,
        )
        if parsed:
            parsed = _normalize_flow(
                q,
                parsed,
                user_plan,
                has_thread_history=ctx.is_continuation,
            )
            if user_plan != Plan.PRO:
                parsed.answer_model = "lite"
            return parsed
    except Exception:
        logger.exception("llm flow router failed")

    fallback = LlmFlowDecision(
        flow="search_rag",
        needs_search=True,
        answer_model="lite",
        reason="llm_router_fallback",
    )
    return _normalize_flow(
        q,
        fallback,
        user_plan,
        has_thread_history=ctx.is_continuation,
    )
