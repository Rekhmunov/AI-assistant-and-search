"""Проверка ответа: не должен быть списком ссылок вместо фактов."""

import re

_DELEGATION_RE = re.compile(
    r"посетите\s+сайт|перейдите\s+на|воспользуйтесь\s+(?:сервисом|ресурсом)|"
    r"загляните\s+на|проверьте\s+на\s+сайте|можно\s+найти\s+на\s+сайте|"
    r"https?://",
    re.I,
)

_NUMBER_RE = re.compile(r"-?\d{1,2}\s*°|-?\d{1,2}\s*град|температур[аы]?\s*[-−]?\d", re.I)


def is_link_delegation_answer(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    if not _DELEGATION_RE.search(text):
        return False
    # Есть ссылки/отсылки, но почти нет конкретных цифр — плохой ответ
    return _NUMBER_RE.search(text) is None


def strict_answer_addon() -> str:
    return (
        "\n\nКРИТИЧНО: не перечисляй сайты и URL. "
        "Дай только факты из источников и выдержек со страниц. "
        "Если цифр нет — одной фразой скажи, что в выдаче нет прогноза, без списка порталов."
    )
