"""Basic HTML sanitization for blog content."""

from __future__ import annotations

import re

_SCRIPT_RE = re.compile(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", re.I)
_STYLE_RE = re.compile(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", re.I)
_ON_ATTR_RE = re.compile(r'\s+on\w+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)', re.I)
_JS_HREF_RE = re.compile(r'\shref\s*=\s*"\s*javascript:[^"]*"', re.I)


def sanitize_blog_html(html: str) -> str:
    text = (html or "").strip() or "<p></p>"
    text = _SCRIPT_RE.sub("", text)
    text = _STYLE_RE.sub("", text)
    text = _ON_ATTR_RE.sub("", text)
    text = _JS_HREF_RE.sub("", text)
    return text


def estimate_reading_time_min(html: str) -> int:
    plain = re.sub(r"<[^>]+>", " ", html or "")
    words = len(plain.split())
    return max(1, round(words / 180))
