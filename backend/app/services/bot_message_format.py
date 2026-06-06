"""Определение формата текста для MAX Bot API (markdown / html)."""

from __future__ import annotations

import re

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.IGNORECASE)
_MARKDOWN_RE = re.compile(
    r"(\*\*.+\*\*|__.+__|~~.+~~|\+\+.+?\+\+|\[.+\]\([^)]+\)|`[^`]+`|\^\^.+?\^\^)",
    re.DOTALL,
)


def detect_max_text_format(text: str) -> str | None:
    """Вернуть format для MAX API или None для обычного текста."""
    if _HTML_TAG_RE.search(text):
        return "html"
    if _MARKDOWN_RE.search(text):
        return "markdown"
    return None
