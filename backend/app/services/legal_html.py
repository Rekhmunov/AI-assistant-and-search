"""Безопасная очистка HTML для юридических документов."""

from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_EVENT_ATTR_RE = re.compile(r"\s+on[a-z]+\s*=\s*([\"']).*?\1", re.I)
_JS_HREF_RE = re.compile(r"href\s*=\s*([\"'])\s*javascript:.*?\1", re.I)


def sanitize_legal_html(html: str) -> str:
    text = (html or "").strip()
    if not text:
        return "<p></p>"
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _EVENT_ATTR_RE.sub("", text)
    text = _JS_HREF_RE.sub('href="#"', text)
    return text
