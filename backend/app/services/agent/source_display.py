"""Подготовка источников поиска для UI Glosix (как в обычном треде)."""

from __future__ import annotations

import re
from typing import Any

_SOURCES_FOOTER_RE = re.compile(
    r"\n{1,2}Источники:\s*(?:\n\[\d+\][^\n]*)+\s*$",
    re.IGNORECASE,
)


def strip_sources_footer(text: str) -> str:
    """Убирает текстовый блок «Источники:» в конце ответа — он дублирует UI."""
    body = (text or "").strip()
    if not body:
        return ""
    return _SOURCES_FOOTER_RE.sub("", body).rstrip()


def _normalize_source_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    if not url:
        return None
    index = raw.get("index")
    try:
        idx = int(index) if index is not None else 0
    except (TypeError, ValueError):
        idx = 0
    title = str(raw.get("title") or raw.get("domain") or "Источник").strip()
    domain = str(raw.get("domain") or "").strip()
    snippet = str(raw.get("snippet") or "").strip()
    return {
        "index": idx,
        "url": url,
        "title": title,
        "snippet": snippet,
        "domain": domain,
    }


def extract_sources_from_tool_trace(tool_trace: list[dict]) -> list[dict[str, Any]] | None:
    """Последний успешный web_search в цикле агента."""
    for item in reversed(tool_trace):
        if item.get("tool") != "web_search" or not item.get("ok"):
            continue
        result = item.get("result")
        if not isinstance(result, dict):
            continue
        raw_sources = result.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            continue
        out: list[dict[str, Any]] = []
        for raw in raw_sources:
            norm = _normalize_source_item(raw)
            if norm:
                out.append(norm)
        if out:
            for i, src in enumerate(out, start=1):
                if not src.get("index"):
                    src["index"] = i
            return out
    return None


def prepare_agent_reply_for_ui(reply: str, tool_trace: list[dict]) -> tuple[str, list[dict[str, Any]] | None]:
    """Текст без дублирующего футера + structured sources для Message.sources."""
    sources = extract_sources_from_tool_trace(tool_trace)
    body = (reply or "").strip()
    if sources:
        body = strip_sources_footer(body)
    return body, sources
