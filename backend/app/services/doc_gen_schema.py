"""Валидация JSON-структуры документа от LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.constants.doc_gen import MAX_DOC_SECTIONS, MAX_DOC_TABLES, MAX_DOC_PARAGRAPHS_PER_SECTION


@dataclass
class DocSection:
    heading: str
    paragraphs: list[str]


@dataclass
class DocTable:
    caption: str
    headers: list[str]
    rows: list[list[str]]


@dataclass
class DocumentStructure:
    title: str
    sections: list[DocSection] = field(default_factory=list)
    tables: list[DocTable] = field(default_factory=list)


class DocumentStructureError(ValueError):
    pass


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def _extract_json_blob(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise DocumentStructureError("empty_llm_response")
    match = _JSON_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _as_str_list(value: Any, *, max_items: int, max_len: int = 8000) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s[:max_len])
    return out


def parse_document_structure(raw: str) -> DocumentStructure:
    try:
        data = json.loads(_extract_json_blob(raw))
    except json.JSONDecodeError as e:
        raise DocumentStructureError("invalid_json") from e
    if not isinstance(data, dict):
        raise DocumentStructureError("root_not_object")

    title = str(data.get("title") or "").strip()
    if not title:
        raise DocumentStructureError("missing_title")

    sections: list[DocSection] = []
    for item in (data.get("sections") or [])[:MAX_DOC_SECTIONS]:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading") or "").strip()
        paragraphs = _as_str_list(
            item.get("paragraphs"),
            max_items=MAX_DOC_PARAGRAPHS_PER_SECTION,
        )
        if not heading and not paragraphs:
            continue
        sections.append(DocSection(heading=heading, paragraphs=paragraphs))

    tables: list[DocTable] = []
    for item in (data.get("tables") or [])[:MAX_DOC_TABLES]:
        if not isinstance(item, dict):
            continue
        headers = _as_str_list(item.get("headers"), max_items=20, max_len=200)
        rows_raw = item.get("rows") or []
        rows: list[list[str]] = []
        if isinstance(rows_raw, list):
            for row in rows_raw[:80]:
                if isinstance(row, list):
                    rows.append([str(c).strip()[:500] for c in row[:20]])
        if not headers and not rows:
            continue
        tables.append(
            DocTable(
                caption=str(item.get("caption") or "").strip()[:200],
                headers=headers,
                rows=rows,
            )
        )

    if not sections and not tables:
        raise DocumentStructureError("empty_body")

    return DocumentStructure(title=title[:300], sections=sections, tables=tables)
