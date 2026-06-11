"""Подстановка результата web_search, если модель отказала после успешного поиска."""

from __future__ import annotations


def latest_web_search_text(tool_trace: list[dict]) -> str | None:
    for item in reversed(tool_trace):
        if item.get("tool") != "web_search" or not item.get("ok"):
            continue
        result = item.get("result")
        if isinstance(result, dict):
            text = str(result.get("text") or "").strip()
            if text:
                return text
    return None


def reply_defers_after_search(reply: str) -> bool:
    low = (reply or "").lower()
    markers = (
        "не могу искать",
        "не могу найти",
        "не умею искать",
        "моя задача",
        "настройк",
        "автоматизац",
        "только помогаю с настройкой",
        "не поддержива",
    )
    return any(m in low for m in markers)


def prefer_web_search_answer(reply: str, tool_trace: list[dict]) -> str:
    """Если web_search уже вернул ответ с источниками — не отбрасывать его из-за отказа LLM."""
    search_text = latest_web_search_text(tool_trace)
    if not search_text:
        return reply
    body = (reply or "").strip()
    if reply_defers_after_search(body):
        return search_text
    if len(body) < 40 and len(search_text) > len(body):
        return search_text
    return reply
