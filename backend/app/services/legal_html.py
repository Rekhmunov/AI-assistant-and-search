"""Безопасная очистка HTML для юридических документов."""

from __future__ import annotations

from app.services.html_sanitize import sanitize_legal_rich_html


def sanitize_legal_html(html: str) -> str:
    return sanitize_legal_rich_html(html, empty_default="<p></p>")
