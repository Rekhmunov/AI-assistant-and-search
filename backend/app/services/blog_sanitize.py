"""Basic HTML sanitization for blog content."""

from __future__ import annotations

import re

from app.services.html_sanitize import sanitize_rich_html


def sanitize_blog_html(html: str) -> str:
    return sanitize_rich_html(html, empty_default="<p></p>")


def estimate_reading_time_min(html: str) -> int:
    plain = re.sub(r"<[^>]+>", " ", html or "")
    words = len(plain.split())
    return max(1, round(words / 180))
