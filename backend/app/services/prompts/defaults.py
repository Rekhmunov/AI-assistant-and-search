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

REWRITER_USER = """Ты — модуль анализа вопроса перед веб-поиском (как исследователь). Язык: русский.

Вопрос пользователя:
{query}

История диалога:
{history_text}

Продолжение диалога: {continuation_label}

Задачи:
1. Пойми, какие факты нужны пользователю (сами факты, не «где искать»).
2. intent: factual_current | howto | compare_analyze | document | edit_prior | chitchat
3. fact_slots — какие типы структурированных данных нужны (можно несколько или []):
   - fx_rate — только курс валют / обмен (USD, EUR, ЦБ), НЕ «курс на похудение», НЕ «курс обучения»
   - weather_now — погода, температура, осадки в городе
   - company_financial — оборот, выручка, прибыль, ИНН, отчётность компании
   - course_program — программа обучения, похудения, тренировок, «курс по/на …»
   - [] — общие темы (тренды, анализ рынка, новости, определения) без слотов выше
   Примеры: «курс доллара» → ["fx_rate"]; «курс на похудение» → ["course_program"]; «прогноз продаж» → []; «погода в Иваново» → ["weather_now"]
4. search_queries: 1–3 запроса в Yandex со словами, по которым на странице будут цифры/факты (не «где посмотреть», не список сайтов).
   Для fx_rate добавь валюту и «ЦБ»/«котировка»; для weather_now — город, дату, «температура»; для course_program — «программа», «план», «похудение»/тему.
   Если в вопросе «подробный», «детальный», «пошаговый», «план» — запросы на страницы с конкретным планом (недели, меню, тренировки), не общие статьи «советы».
5. «А завтра?» / «а там?» — полный самодостаточный запрос из истории.
6. needs_clarification=true только если без параметра (город, дата, компания) факт недостижим; один короткий вопрос. Не подставляй город по умолчанию.
7. how-to: intent=howto, grounding=synthesis, в search_queries — «официальная документация» / «инструкция».
8. grounding — как отвечать после поиска:
   - strict — только курс валют, погода, финансы (слоты fx_rate / weather_now / company_financial): цифры и даты только из [n]
   - hybrid — по умолчанию для «можно ли», продуктов, платформ, IT, архитектуры, объяснений: знания модели + [n] на факты из сети; всегда дай решение по сути
   - synthesis — программы, похудение, пошаговые планы: структура из [n], без выдуманных метрик
   Примеры: «курс USD» → strict; «можно ли напоминания в мессенджере» → hybrid; «напиши функцию на Go» → hybrid; «курс похудения на 4 недели» → synthesis + course_program
9. Для любого названного продукта, сервиса или платформы в search_queries добавь «официальная документация» / «developer docs» / «API».
10. Если needs_clarification=false — минимум один search_queries.

Ответь ТОЛЬКО JSON:
{{"intent": "factual_current", "fact_slots": [], "grounding": "hybrid", "search_queries": ["..."], "needs_clarification": false, "clarification_question": null, "reason": "..."}}"""

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
