"""Проверка ответа: шаблонные отговорки и списки ссылок вместо фактов."""

import re

_DELEGATION_RE = re.compile(
    r"посетите\s+сайт|перейдите\s+на|воспользуйтесь\s+(?:сервисом|ресурсом)|"
    r"загляните\s+на|проверьте\s+на\s+сайте|можно\s+найти\s+на\s+сайте|"
    r"https?://",
    re.I,
)

_TEMPLATE_RE = re.compile(
    r"я\s+—\s+экспертный\s+поисковый|я\s+не\s+умею\s+программ|"
    r"я\s+не\s+могу\s+программ|только\s+поисковый\s+ассистент|"
    r"создан(?:а)?\s+для\s+поиска\s+и\s+предоставления\s+информации|"
    r"к\s+сожалению[^.\n]{0,80}(?:не\s+могу|нет|не\s+имею)|"
    r"у\s+меня\s+нет\s+(?:специализ|знаний|опыта|доступ)|"
    r"не\s+имею\s+специализ|не\s+разбираюсь|"
    r"рекомендую\s+обратиться|"
    r"выполните\s+поиск|"
    r"обратитесь\s+к\s+специалист|"
    r"финансовые\s+портал|"
    r"какой\s+ресурс\s+вы\s+хотел|"
    r"можете\s+узнать\s+актуальный\s+курс|"
    r"предоставляет\s+официальные\s+курсы\s+валют|"
    r"давайте\s+попробуем\s+найти|"
    r"давайте\s+поищем|"
    r"могу\s+найти\s+(?:актуальн|информац)|"
    r"могу\s+использовать\s+такие\s+ресурс|"
    r"я\s+могу\s+использовать|"
    r"однако\s+я\s+могу\s+найти|"
    r"предоставить\s+вам\s+ответ,\s+основанный",
    re.I,
)

_NUMBER_RE = re.compile(
    r"-?\d{1,2}\s*°|-?\d{1,2}\s*град|температур[аы]?\s*[-−]?\d|\d{4}|\d+[\.,]\d+",
    re.I,
)


def is_link_delegation_answer(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    if not _DELEGATION_RE.search(text):
        return False
    return _NUMBER_RE.search(text) is None


def is_refusal_or_process_talk(text: str) -> bool:
    """Отказ от темы или рассказ о поиске вместо ответа."""
    if not text or len(text.strip()) < 30:
        return False
    head = text[:600]
    if _TEMPLATE_RE.search(head):
        return True
    if re.search(r"https?://", head) and len(text.split()) < 120:
        if _TEMPLATE_RE.search(text) or "могу" in head.lower() and "найти" in head.lower():
            return True
    return False


def is_template_evasion(text: str) -> bool:
    """Ответ-отговорка без содержания: шаблоны, только ссылки, отказ без фактов."""
    if not text or len(text.strip()) < 40:
        return False
    if is_refusal_or_process_talk(text):
        return True
    if is_link_delegation_answer(text):
        return True
    urls = len(re.findall(r"https?://", text))
    if urls >= 1 and urls >= len(re.findall(r"\[\d+\]", text)) and len(text.split()) < 100:
        if "могу" in text.lower() or "давайте" in text.lower():
            return True
    if urls >= 2 and len(text.split()) < 90 and _NUMBER_RE.search(text) is None:
        return True
    return False


def strict_answer_addon() -> str:
    return (
        "\n\nКРИТИЧНО: источники уже подобраны — отвечай сразу по теме с [1], [2]. "
        "Запрещены: «к сожалению», «нет знаний/специализации», «давайте найдём», голые URL. "
        "Не описывай процесс поиска. Точные цифры и даты — только из фактов и [n]."
    )


def image_display_answer_addon() -> str:
    return (
        "\n\nПользователь просит показать фото или картинку. "
        "Glosix не встраивает изображения в чат — вместо этого дай развёрнутый текстовый ответ "
        "по теме из источников [n]: описание, характеристики, интересные факты. "
        "Запрещено отказываться («не могу показать фото», «не работаю с изображениями», "
        "«нет доступа к картинкам»). Можно одной фразой упомянуть, что картинки в чат не "
        "вставляются, но сразу переходи к содержательному ответу."
    )


def vision_capability_answer_addon() -> str:
    return (
        "\n\nВопрос про анализ фото без прикреплённого снимка. "
        "Glosix умеет анализировать изображения, когда пользователь прикрепляет фото к сообщению "
        "(калории/состав блюда, текст на упаковке, описание объектов). "
        "Сейчас фото нет — коротко объясни это и попроси прикрепить снимок для анализа. "
        "Не пиши «не могу по фото» или «нет vision». "
        "Не используй цитаты [1], [2] — в этом режиме источников нет."
    )


def direct_system_addons(query: str) -> str:
    from app.services.search_query import is_vision_capability_question

    if is_vision_capability_question(query):
        return vision_capability_answer_addon()
    return ""


def hybrid_answer_addon() -> str:
    return (
        "\n\nРежим hybrid: опирайся на свои знания модели для кода, объяснений, структуры текста "
        "и best practices. Источники [n] ниже — для актуальных фактов, версий, цен, дат и цитат. "
        "Цифры, даты, курсы, температуры — только из [n] или блока фактов; общие знания — без [n]. "
        "Если в источниках мало полезного — не отказывайся: ответь по сути из знаний, поиск — дополнение."
    )


def search_answer_addon(
    *,
    grounding: str,
    strict_facts: bool = False,
    fact_slots: list[str] | None = None,
    intent_howto: bool = False,
) -> str:
    from app.services.facts.grounding import effective_grounding_for_prompt

    mode = effective_grounding_for_prompt(
        grounding,  # type: ignore[arg-type]
        fact_slots,
        intent_howto=intent_howto,
    )
    if mode == "hybrid":
        return hybrid_answer_addon()
    if mode == "synthesis":
        return answer_addon_for_slots(fact_slots or [], synthesis=True)
    if strict_facts or mode == "strict":
        return strict_answer_addon()
    return ""


def answer_addon_for_slots(fact_slots: list[str], *, synthesis: bool = False) -> str:
    if synthesis:
        return (
            "\n\nРежим плана (курс / похудение / how-to): собери развёрнутый пошаговый ответ из источников [n]. "
            "Обязательны блоки (питание, тренировки, режим) с конкретикой из материалов. "
            "Не выдумывай точные ккал, вес или сроки, которых нет в [n]. "
            "Не сокращай до общих советов «ешьте меньше, занимайтесь спортом». "
            "Запрещены отказы и «давайте поищем»."
        )
    return strict_answer_addon()
