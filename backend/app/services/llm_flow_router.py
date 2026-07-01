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
    "image_edit",
    "image_compose",
    "export_chat_document",
    "compress_pdf",
    "convert_pdf",
    "compress_image",
    "image_to_pdf",
    "split_pdf",
]

_FLOW_JSON_RE = re.compile(r"\{[\s\S]*\}")


@dataclass
class LlmFlowDecision:
    flow: ServiceFlow
    needs_search: bool
    answer_model: Literal["lite", "pro"]
    reason: str
    force_yandex: bool = False
    high_quality: bool = False
    intent: str = "factual_current"


_ROUTER_SYSTEM = """Ты маршрутизатор запросов в Glosix (умный ассистент с веб-поиском и файлами).

Верни ТОЛЬКО JSON без markdown:
{
  "flow": "search_rag" | "chat" | "image_generate" | "image_edit" | "image_compose" | "export_chat_document" | "compress_pdf" | "convert_pdf" | "compress_image" | "image_to_pdf" | "split_pdf",
  "needs_search": true/false,
  "answer_model": "lite" | "pro",
  "reason": "кратко по-русски",
  "force_yandex": true/false,
  "high_quality": true/false,
  "intent": "factual_current" | "howto" | "document" | "edit_prior" | "compare_analyze" | "chitchat"
}

intent — тип запроса для выбора глубины ответа:
- factual_current — обычный факт, событие, определение, поиск в интернете
- howto — «как сделать», «как настроить», «как установить», пошаговые инструкции
- document — к сообщению прикреплён файл/документ, пользователь просит его проанализировать
- edit_prior — правка предыдущего ответа в треде: «перефразируй», «сократи», «переведи», «перепиши», «резюмируй», «добавь раздел». Только если тред уже содержит историю.
- compare_analyze — сравнение, анализ, оценка: «сравни X и Y», «проанализируй», «плюсы и минусы», «подробный разбор»
- chitchat — светская беседа, приветствие, «спасибо», «кто ты», «что умеешь»

high_quality = true — только для flow=image_generate, когда пользователь явно просит высокое качество или 2K:
- Слова-маркеры: «2к», «2K», «в 2к», «высокое качество», «лучшее качество», «максимальное качество», «HD», «высокое разрешение», «большое разрешение».
- По умолчанию false. Не ставить true если пользователь просто просит «нарисуй» без уточнения качества.

answer_model = "pro" — запрос требует глубокого анализа или синтеза нескольких источников:
- Сравнение с оценкой: «сравни X и Y», «что лучше A или B», «чем отличается» (с просьбой оценить)
- Аналитика: «проанализируй», «оцени плюсы и минусы», «разбери по критериям»
- Причины и связи: «почему X влияет на Y», «каковы причины», «как это связано с»
- Выбор и стратегия: «как выбрать», «что учесть при», «какие риски», «стоит ли»
- Обзоры: «лучшие решения для X», «обзор рынка Y», «топ инструментов»
- Сложные механизмы: «как устроена система X», «как работает процесс», «как организовать»

answer_model = "pro" ТАКЖЕ для запросов с force_yandex=true (новости и текущие события):
- Результаты Яндекса требуют синтеза: «матчи сегодня», «курс доллара», «погода», «новости»
- Lite-модели плохо извлекают конкретные факты из поисковой выдачи и часто отвечают уклончиво
- Всегда ставь pro когда force_yandex=true — система сама даунгрейдит до lite для нон-про пользователей

answer_model = "lite" — всё остальное:
- Простые факты без поиска: «кто такой X», «расшифруй аббревиатуру», «что такое X»
- Запросы с одним конкретным ответом, не требующие синтеза
- Создание текста/кода (flow=chat)

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
- image_generate — пользователь просит нарисовать/сгенерировать ВИЗУАЛЬНОЕ изображение/картинку с нуля.
  Явные глаголы-маркеры: «нарисуй», «нарисуй картинку», «сгенерируй изображение/картинку/арт», «сделай арт», «создай иллюстрацию».
  НЕ использовать если слово «фото» без глагола генерации («фото кота» — это поиск → search_rag).
  НЕ использовать если: «сгенерируй текст/отчёт/таблицу/документ/список/план» — это chat или search_rag.
- image_edit — пользователь просит ИЗМЕНИТЬ изображение: прикреплено фото с инструкцией трансформировать его, ИЛИ в треде есть сгенерированное ранее изображение и пользователь просит его изменить. Маркеры: «сделай мультяшным», «сделай ч/б», «убери фон», «измени цвет», «добавь элемент», «перекрась», «измени стиль», «нарисуй в стиле», «сделай другим», «преврати в». НЕ использовать если пользователь просит ОПИСАТЬ или ПРОАНАЛИЗИРОВАТЬ фото (что на фото → search_rag). НЕ использовать если прикреплены 2+ фото (→ image_compose).
- image_compose — пользователь прикрепил 2+ изображения И просит их ОБЪЕДИНИТЬ/СКОМПОНОВАТЬ: «добавь модель на кровать», «помести кота на фон», «объедини фото», «наложи», «совмести». НЕ использовать если прикреплены фото для анализа.
- export_chat_document — оформить УЖЕ написанный в переписке текст (ответ выше, текст выше, преобразуй в markdown). Не переписывать содержание.
- compress_pdf — пользователь ЯВНО просит сжать конкретный PDF-файл (прикреплён или упомянут). НЕ использовать если это вопрос о возможностях («умеешь ли», «можешь ли», «что умеешь»).
- convert_pdf — пользователь ЯВНО просит конвертировать конкретный PDF в JPG. НЕ использовать если это вопрос о возможностях.
- compress_image — пользователь просит сжать, уменьшить размер или оптимизировать изображение/фото.
  Маркеры: «сожми фото», «уменьши размер картинки», «сделай файл легче», «оптимизируй фото», «для сайта», «для соцсетей».
  ТОЛЬКО если прикреплено изображение (jpg/png/webp/heic) или оно есть в треде. НЕ использовать если это вопрос о возможностях.
- image_to_pdf — пользователь просит конвертировать изображение(я) в PDF.
  Маркеры: «сделай PDF из фото», «конвертируй фото в PDF», «объедини фото в PDF», «скан в PDF», «фото в PDF».
  ТОЛЬКО если прикреплено одно или несколько изображений или они есть в треде. НЕ использовать если это вопрос о возможностях.
- split_pdf — пользователь просит разбить, разделить или нарезать PDF на части/файлы.
  Маркеры: «разбей на части», «раздели PDF», «по 10 страниц», «нарежь на файлы», «каждые N страниц», «разбить пополам», «на отдельные страницы».
  ТОЛЬКО если прикреплён PDF или он есть в треде. НЕ использовать если это вопрос о возможностях.

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

Создание документов → chat, needs_search=false:
- «напиши оферту», «создай договор», «сделай заявление», «составь инструкцию».
- Если нужны актуальные данные (цены, нормы, ставки) — search_rag вместо chat.

Экспорт → export_chat_document, needs_search=false:
- «сгенерируй текст выше в документ», «оформи ответ выше», «экспортируй ответ».
- Только если в контексте треда есть предыдущий ответ для экспорта.

Вложения (фото/изображения):
КРИТИЧЕСКИ ВАЖНО — различай анализ и редактирование:

АНАЛИЗ (→ search_rag, needs_search=true): пользователь прикрепил фото и СПРАШИВАЕТ о содержимом:
- «что на фото», «опиши», «что изображено», «найди ошибки»
- «сколько калорий», «что это за блюдо», «какое животное»
- «переведи текст», «что написано», «прочитай»
- «оцени», «проанализируй», «расскажи о», «что за место»
- Любое СУЩЕСТВИТЕЛЬНОЕ + ВОПРОС о его содержании

РЕДАКТИРОВАНИЕ (→ image_edit): пользователь хочет ВИЗУАЛЬНО ТРАНСФОРМИРОВАТЬ изображение.
Два случая: (A) прикреплено ОДНО фото + инструкция изменить; (B) в треде есть сгенерированное изображение + инструкция изменить.

ВАЖНО: если прикреплено фото И есть любой маркер трансформации → image_edit,
даже если запрос содержит слова «создай», «сгенерируй», «нарисуй», «сделай снимок».

Маркеры трансформации:
- Стиль: «мультяшным», «аниме», «в стиле», «пикселизируй», «маслом», «акварелью», «набросок», «карандашом»
- Из фото: «из этого фото», «по этому фото», «из фото», «снимок из фото», «по фотографии»
- Трансформация: «преврати в», «сделай версию», «сделай похожим», «переделай», «измени»
- Цвет/тон: «ч/б», «чёрно-белым», «перекрась», «измени цвет», «тёплым», «холодным»
- Редактура: «убери фон», «добавь элемент», «дорисуй», «обрежь», «улучши качество»

НЕ использовать если пользователь только СПРАШИВАЕТ о содержимом (→ search_rag).
НЕ использовать если прикреплены 2+ фото с инструкцией объединить (→ image_compose).

КОМПОЗИЦИЯ (→ image_compose): прикреплены 2+ изображения + инструкция их объединить:
- «добавь [объект с фото2] на [фото1]», «помести», «наложи», «совмести»
- «сделай так чтобы [модель с фото2] была на [кровати с фото1]»

ФАЙЛОВЫЕ ОПЕРАЦИИ — эти правила имеют приоритет над всеми остальными:

Если прикреплён PDF или в запросе упомянуто «PDF» / «ПДФ» / «пдф»:
  → «сожми», «уменьши», «сделай легче», «меньше весить», «уменьши размер» → compress_pdf
  → «конвертируй в JPG», «в картинки», «в изображение», «в jpg» → convert_pdf
  → «разбей», «раздели», «нарежь», «по N страниц», «на части», «на файлы» → split_pdf
  → «что написано», «проанализируй», «найди», «переведи», «что в документе», «содержимое» → search_rag
  → любой другой запрос с PDF без явной операции → search_rag
  НЕ использовать compress_image, image_edit, image_to_pdf если прикреплён PDF.

Если прикреплено изображение (jpg/png/webp/heic — НЕ pdf):
  → «сожми», «уменьши размер», «оптимизируй», «для сайта», «сделай файл легче» → compress_image
  → «в PDF», «конвертируй в PDF», «объедини в PDF», «скан в PDF» → image_to_pdf
  → маркеры трансформации стиля/цвета/редактуры → image_edit
  → 2+ изображения + объединить/наложить → image_compose
  → вопрос о содержимом («что на фото», «опиши», «переведи текст») → search_rag
  НЕ использовать compress_pdf если прикреплено изображение (не PDF).

Файлы docx/txt/xlsx → search_rag, needs_search=true (анализ содержимого).

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
        "image_edit",
        "image_compose",
        "export_chat_document",
        "compress_pdf",
        "convert_pdf",
        "compress_image",
        "image_to_pdf",
        "split_pdf",
    ):
        return None
    needs_search = bool(data.get("needs_search"))
    model = str(data.get("answer_model") or "lite").strip()
    if model not in ("lite", "pro"):
        model = "lite"
    reason = str(data.get("reason") or "llm_router")[:200]
    force_yandex = bool(data.get("force_yandex", False))
    high_quality = bool(data.get("high_quality", False))
    _valid_intents = frozenset({
        "factual_current", "howto", "document",
        "edit_prior", "compare_analyze", "chitchat",
    })
    raw_intent = str(data.get("intent") or "factual_current").strip()
    intent = raw_intent if raw_intent in _valid_intents else "factual_current"
    return LlmFlowDecision(
        flow=flow,  # type: ignore[arg-type]
        needs_search=needs_search,
        answer_model=model,  # type: ignore[arg-type]
        reason=reason,
        force_yandex=force_yandex,
        high_quality=high_quality,
        intent=intent,
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
    attachment_types: list[str] | None = None,  # ["pdf", "image", "docx", ...]
) -> LlmFlowDecision:
    """LLM выбирает поток; при ошибке — безопасный search_rag."""
    q = normalize_user_query(query)

    history = format_history_compact(ctx.history, max_turns=3, max_chars=400)
    user_block = f"Запрос пользователя:\n{q}"
    if has_attachments:
        if attachment_types:
            # Передаём точные типы файлов — роутер сможет выбрать правильный флоу
            types_str = ", ".join(attachment_types)
            user_block += f"\n[К сообщению прикреплены файлы: {types_str}]"
        else:
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
