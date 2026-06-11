"""Загрузка документации MAX API для агента."""

from __future__ import annotations

import os
from functools import lru_cache

_DOCS_PATH = os.path.join(os.path.dirname(__file__), "../../data/max_api_docs.md")

_SECTION_ALIASES: dict[str, list[str]] = {
    "overview": ["общее", "overview", "обзор", "общая", "лимит", "http-код"],
    "messages": ["сообщен", "messages", "отправ", "текст", "format", "кнопк", "keyboard", "вложен"],
    "chats": ["чат", "chat", "канал", "channel", "участник", "member", "групп"],
    "events": ["событи", "event", "update", "webhook", "бот_добавлен", "bot_added", "message_created"],
    "permissions": ["право", "permission", "админ", "admin", "модер"],
    "media": ["медиа", "media", "файл", "file", "изображен", "image", "фото", "photo", "видео", "video"],
    "limits": ["лимит", "limit", "ограничен", "rps", "таймаут", "timeout"],
    "capabilities": ["умеет", "возможност", "capabilities", "что может", "поддерживает"],
    "chat_id": ["chat_id", "как получить id", "получени", "ссылк", "link"],
}


@lru_cache(maxsize=1)
def _load_full_docs() -> str:
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "max_api_docs.md"))
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Документация MAX API недоступна."


def get_max_docs(section: str | None = None) -> str:
    """Возвращает документацию MAX API целиком или конкретный раздел."""
    full = _load_full_docs()
    if not section:
        return full

    key = (section or "").strip().lower()

    # Ищем нужный раздел по ключевым словам
    matched_headers: list[str] = []
    for sec_name, keywords in _SECTION_ALIASES.items():
        if any(kw in key for kw in keywords):
            matched_headers.append(sec_name)

    if not matched_headers:
        return full

    # Разбиваем документ на разделы по заголовкам второго уровня (##)
    import re
    parts = re.split(r"\n(?=## )", full)
    result_parts: list[str] = []

    for part in parts:
        part_lower = part.lower()
        if any(
            any(kw in part_lower for kw in _SECTION_ALIASES.get(h, []))
            for h in matched_headers
        ):
            result_parts.append(part.strip())

    if result_parts:
        return "\n\n---\n\n".join(result_parts)

    return full
