"""Защита от ответов о новостях/поиске без реального вызова web_search."""

from __future__ import annotations

import re

_SEARCH_TOOLS = frozenset({"web_search", "build_news_post"})

_LIVE_SEARCH_MARKERS = (
    "новост",
    "найди",
    "поиск",
    "что нового",
    "актуальн",
    "свеж",
    "в интернет",
    "погода",
    "курс",
    "котиров",
    "сегодня",
    "вчера",
    "последн",
    "что происходит",
    "что случилось",
)

_HALLUCINATION_MARKERS = (
    "[пример",
    "пример новости",
    "гипотетическ",
    "выдуманн",
    "если хочешь настроить регулярную рассылку",
    "предложу расписание",
)


def user_needs_live_search(text: str) -> bool:
    low = (text or "").lower()
    if not low.strip():
        return False
    if any(m in low for m in _LIVE_SEARCH_MARKERS):
        return True
    if re.search(r"\bнайд\w*\b", low) and re.search(r"\b(новост|информац|данн|факт)\w*\b", low):
        return True
    return False


def search_tools_ran_ok(tool_trace: list[dict]) -> bool:
    for item in tool_trace:
        if item.get("tool") in _SEARCH_TOOLS and item.get("ok"):
            result = item.get("result")
            if isinstance(result, dict) and (result.get("text") or result.get("sources")):
                return True
    return False


def reply_looks_hallucinated_search(reply: str) -> bool:
    low = (reply or "").lower()
    return any(m in low for m in _HALLUCINATION_MARKERS)


def must_run_search_before_reply(
    *,
    user_text: str,
    reply: str,
    tool_trace: list[dict],
) -> bool:
    if not user_needs_live_search(user_text):
        return False
    if search_tools_ran_ok(tool_trace):
        return False
    if reply_looks_hallucinated_search(reply):
        return True
    if len((reply or "").strip()) > 80:
        return True
    return False
