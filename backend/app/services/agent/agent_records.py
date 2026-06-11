"""Универсальное хранилище записей агента (затраты, события)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.agent import AgentInstance

MAX_RECORDS_PER_TABLE = 5000


def _tables(cfg: dict) -> dict[str, list]:
    raw = cfg.get("agent_records")
    return dict(raw) if isinstance(raw, dict) else {}


def store_record(
    agent: AgentInstance,
    table: str,
    data: dict[str, Any],
    *,
    author: str = "",
    chat_id: int | None = None,
) -> dict[str, Any]:
    name = (table or "default").strip().lower()[:64]
    cfg = dict(agent.config or {})
    tables = _tables(cfg)
    rows = list(tables.get(name) or [])
    entry = dict(data)
    entry.setdefault("at", datetime.now(timezone.utc).isoformat())
    if author:
        entry["author"] = author
    if chat_id is not None:
        entry["chat_id"] = chat_id
    rows.append(entry)
    tables[name] = rows[-MAX_RECORDS_PER_TABLE:]
    cfg["agent_records"] = tables
    agent.config = cfg
    return entry


def query_records(
    agent: AgentInstance,
    table: str,
    *,
    category: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    name = (table or "default").strip().lower()[:64]
    cfg = dict(agent.config or {})
    rows = list(_tables(cfg).get(name) or [])
    if category:
        cat_low = category.lower()
        rows = [r for r in rows if str(r.get("category", "")).lower() == cat_low]
    return rows[-limit:]
