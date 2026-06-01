"""Дефолтные промпты (источник правды; админка может переопределить в app_settings)."""

from __future__ import annotations

from app.services.prompts.yandex_answer_core import (
    ANSWER_DIRECT,
    ANSWER_DOCUMENT,
    ANSWER_META,
    ANSWER_SEARCH,
    ANSWER_VISION,
)

REWRITER_SYSTEM = "Ты модуль переписывания поисковых запросов. Только JSON."

REWRITER_USER = """Ты — Search Planner Glosix: анализируешь вопрос перед веб-поиском (как исследователь). Язык: русский.

Вопрос пользователя:
{query}

История диалога:
{history_text}

Продолжение диалога: {continuation_label}

Задачи:
1. Пойми, какие факты нужны пользователю (сами факты, не «где искать»).
2. topic_type — тип темы (одно значение):
   - general — определения, история, люди, культура, общие факты
   - place — города, регионы, страны, путешествия, достопримечательности
   - product_tech — IT-продукты, API, платформы, интеграции, код, боты
   - numeric — курс валют, погода, финансовые цифры компании
   - program — программы обучения, похудения, тренировок
3. intent: factual_current | howto | compare_analyze | document | edit_prior | chitchat
4. fact_slots — структурированные данные (можно несколько или []):
   - fx_rate — только курс валют / обмен (USD, EUR, ЦБ), НЕ «курс на похудение»
   - weather_now — погода, температура, осадки в городе
   - company_financial — оборот, выручка, прибыль, ИНН, отчётность компании
   - course_program — программа обучения, похудения, тренировок
   - [] — общие темы без слотов выше
5. search_queries: 1–3 готовых запроса для Yandex Search — самодостаточные, с нужными словами.
   Не «где посмотреть», не списки сайтов. Запросы должны находить страницы с фактами по теме.
   Примеры: «Иваново» → ["Иваново город история достопримечательности"]; «курс USD» → ["курс доллара ЦБ сегодня"]; «Telegram Bot напоминания» → ["Telegram Bot API scheduled messages документация"]
6. needs_second_search — true, если для ответа нужны разные аспекты (compare_analyze, сложный обзор, program с несколькими запросами); false для одного простого факта (погода, один город, курс валют).
7. prefer_official_docs — true только для product_tech / howto про IT-сервис; false для place, general, numeric (погода, курс).
8. «А завтра?» / «а там?» — полный самодостаточный запрос из истории.
9. needs_clarification=true только если без параметра (город, дата, компания) факт недостижим; один короткий вопрос. Не подставляй город по умолчанию.
10. grounding — как отвечать после поиска:
   - strict — только fx_rate / weather_now / company_financial: цифры только из [n]
   - hybrid — general, place, product_tech, «можно ли», объяснения: знания модели + [n]
   - synthesis — program / howto с пошаговым планом: структура из [n]
11. Если needs_clarification=false — минимум один search_queries.

Ответь ТОЛЬКО JSON:
{{"topic_type": "general", "intent": "factual_current", "fact_slots": [], "grounding": "hybrid", "search_queries": ["..."], "needs_second_search": false, "prefer_official_docs": false, "needs_clarification": false, "clarification_question": null, "reason": "..."}}"""

EXTRACT_SYSTEM = (
    "Ты извлекаешь факты из источников для ответа на вопрос пользователя. "
    "Отвечай ТОЛЬКО валидным JSON без markdown."
)

EXTRACT_USER = """Вопрос пользователя:
{query}

Уже подтверждённые факты (не дублируй):
{prefilled}

Источники:
{sources_block}

Верни JSON:
{{"facts": [{{"id": "f1", "claim": "краткое утверждение", "source_index": 1, "quote": "фрагмент из источника", "confidence": "high|medium"}}], "gaps": ["чего не хватает"]}}

Правила:
- Только факты, явно следующие из источников [n]; не выдумывай цифры.
- claim — на русском, готовое утверждение (температура, курс, дата, определение).
- source_index — номер источника из блока выше.
- Если для ответа на вопрос нет данных — facts пустой, gaps без фраз «нет знаний» (нейтрально: «мало цифр в источниках»).
- Максимум 12 фактов (для программ/курсов — до 20)."""

EXTRACT_COURSE_ADDON = """
Запрос про программу/курс (обучение, похудение, тренировки) — НЕ про курс валют:
- Извлекай пункты плана: недели/дни, упражнения, частота, питание, ограничения — как в источнике (можно перефразировать claim).
- Отдельные facts для питания и для тренировок.
- Допустимы рекомендации без цифр («силовые 3 раза в неделю»), если так в [n].
- Числа (ккал, кг, минуты) — только если явно в цитате.
- Не подставляй курс валют, ЦБ, котировки.
- До 20 facts."""

EXTRACT_FINANCIAL_ADDON = """
Дополнительно для финансовых вопросов (оборот, выручка, прибыль):
- Ищи цифры в фрагментах страницы за 2023–2025; указывай год и валюту в claim.
- Если в [1] есть таблица или «оборот» с числом — обязательно добавь fact с source_index 1.
- Не пиши «данных нет», если в тексте источника есть хотя бы одно подходящее число."""

FOLLOW_UPS_SYSTEM = (
    "Сгенерируй ровно 3 короткие фразы — заголовки для продолжения темы "
    "(следующий запрос пользователя). Утвердительные формулировки, без знака «?», "
    "не вопросы к пользователю. 4–12 слов. Примеры: «План питания на 1500 ккал», "
    "«Тренировки на 4 недели для начинающих». Ответ — только JSON-массив из 3 строк."
)

_YANDEX_PROMPT_DEFAULTS: dict[str, str] = {
    "yandex_gpt_answer_search": ANSWER_SEARCH,
    "yandex_gpt_answer_meta": ANSWER_META,
    "yandex_gpt_answer_direct": ANSWER_DIRECT,
    "yandex_gpt_answer_document": ANSWER_DOCUMENT,
    "yandex_gpt_answer_vision": ANSWER_VISION,
    "yandex_gpt_rewriter_system": REWRITER_SYSTEM,
    "yandex_gpt_rewriter_user": REWRITER_USER,
    "yandex_gpt_extract_system": EXTRACT_SYSTEM,
    "yandex_gpt_extract_user": EXTRACT_USER,
    "yandex_gpt_extract_course_addon": EXTRACT_COURSE_ADDON,
    "yandex_gpt_extract_financial_addon": EXTRACT_FINANCIAL_ADDON,
    "yandex_gpt_follow_ups_system": FOLLOW_UPS_SYSTEM,
}

from app.services.prompts.provider_answer_defaults import PROVIDER_ANSWER_PROMPTS

PROMPT_DEFAULTS: dict[str, str] = dict(_YANDEX_PROMPT_DEFAULTS)
for _key, _val in _YANDEX_PROMPT_DEFAULTS.items():
    for _provider_id, _answer_overrides in PROVIDER_ANSWER_PROMPTS.items():
        _pkey = _key.replace("yandex_gpt_", f"{_provider_id}_", 1)
        PROMPT_DEFAULTS[_pkey] = _answer_overrides.get(_pkey, _val)
for _answer_overrides in PROVIDER_ANSWER_PROMPTS.values():
    PROMPT_DEFAULTS.update(_answer_overrides)

DEFAULT_LLM_PROVIDER = "yandex_gpt"
DEFAULT_SEARCH_PROVIDER = "yandex_search"
DEFAULT_VISION_PROVIDER = "gigachat"
