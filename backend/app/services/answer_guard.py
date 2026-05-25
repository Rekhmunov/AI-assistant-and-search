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
    r"к\s+сожалению[^.\n]{0,60}не\s+могу|"
    r"рекомендую\s+обратиться|"
    r"выполните\s+поиск|"
    r"обратитесь\s+к\s+специалист",
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


def is_template_evasion(text: str) -> bool:
    """Ответ-отговорка без содержания: шаблоны, только ссылки, отказ без фактов."""
    if not text or len(text.strip()) < 40:
        return False
    if _TEMPLATE_RE.search(text):
        return True
    if is_link_delegation_answer(text):
        return True
    urls = len(re.findall(r"https?://", text))
    if urls >= 2 and len(text.split()) < 90 and _NUMBER_RE.search(text) is None:
        return True
    return False


def strict_answer_addon() -> str:
    return (
        "\n\nКРИТИЧНО: ответь как эксперт по найденным материалам. "
        "Не перечисляй сайты, URL и не используй шаблоны отказа. "
        "Сразу дай суть, факты и структуру; если данных мало — что удалось выяснить и один уточняющий вопрос."
    )
