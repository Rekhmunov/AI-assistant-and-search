"""Универсальное хранилище записей агента (затраты, события)."""

from __future__ import annotations

import uuid
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
    entry.setdefault("_id", uuid.uuid4().hex[:12])
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


def delete_record_by_id(
    agent: AgentInstance,
    table: str,
    record_id: str,
) -> bool:
    """Удаляет запись по полю _id. Возвращает True если запись была найдена и удалена."""
    name = (table or "default").strip().lower()[:64]
    cfg = dict(agent.config or {})
    tables = _tables(cfg)
    rows = list(tables.get(name) or [])
    new_rows = [r for r in rows if r.get("_id") != record_id]
    if len(new_rows) == len(rows):
        return False
    tables[name] = new_rows
    cfg["agent_records"] = tables
    agent.config = cfg
    return True


def delete_record(
    agent: AgentInstance,
    table: str,
    *,
    last: bool = False,
    index: int | None = None,
    match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Удаляет запись из таблицы. Возвращает {"deleted": [...], "remaining": N}."""
    name = (table or "default").strip().lower()[:64]
    cfg = dict(agent.config or {})
    tables = _tables(cfg)
    rows = list(tables.get(name) or [])
    deleted: list[dict] = []

    if last:
        if rows:
            deleted.append(rows.pop())
    elif index is not None:
        real_idx = index if index >= 0 else len(rows) + index
        if 0 <= real_idx < len(rows):
            deleted.append(rows.pop(real_idx))
    elif match:
        keep = []
        for row in rows:
            matched = all(
                str(row.get(k, "")).lower() == str(v).lower()
                for k, v in match.items()
            )
            if matched and not deleted:
                deleted.append(row)
            else:
                keep.append(row)
        rows = keep

    tables[name] = rows
    cfg["agent_records"] = tables
    agent.config = cfg
    return {"deleted": deleted, "remaining": len(rows)}
