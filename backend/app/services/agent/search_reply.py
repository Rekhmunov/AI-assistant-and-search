"""Fallback: если LLM вернул пустой ответ после web_search — используем текст поиска."""

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


def prefer_web_search_answer(reply: str, tool_trace: list[dict]) -> str:
    """
    Только если LLM вернул пустой ответ после успешного web_search —
    подставляем текст поиска. Не заменяем ответ LLM по ключевым словам.
    """
    body = (reply or "").strip()
    if body:
        return reply  # LLM что-то написал — доверяем ему
    search_text = latest_web_search_text(tool_trace)
    return search_text or reply
