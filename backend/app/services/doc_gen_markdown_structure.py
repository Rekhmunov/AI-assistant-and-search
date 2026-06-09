"""Разбор markdown-блока ответа в структуру для экспорта Docx/PDF."""

from __future__ import annotations

import re

from app.services.doc_gen_plain import structure_from_plain_text
from app.services.doc_gen_schema import DocSection, DocTable, DocumentStructure

_INLINE_MD_RE = re.compile(
    r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\([^)]+\)"
)
_TABLE_ROW_RE = re.compile(r"^\|?.+\|.+\|?$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$")


def strip_inline_markdown(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        return next(g for g in match.groups() if g is not None)

    return _INLINE_MD_RE.sub(_repl, text).strip()


def _split_table_cells(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [strip_inline_markdown(cell.strip()) for cell in raw.split("|")]


def _parse_table_block(lines: list[str], start: int) -> tuple[DocTable | None, int]:
    if start >= len(lines):
        return None, start
    if not _TABLE_ROW_RE.match(lines[start].strip()):
        return None, start

    header_line = lines[start].strip()
    next_idx = start + 1
    if next_idx < len(lines) and _TABLE_SEP_RE.match(lines[next_idx].strip()):
        next_idx += 1

    headers = _split_table_cells(header_line)
    rows: list[list[str]] = []
    idx = next_idx
    while idx < len(lines):
        line = lines[idx].strip()
        if not line or not _TABLE_ROW_RE.match(line):
            break
        if _TABLE_SEP_RE.match(line):
            idx += 1
            continue
        rows.append(_split_table_cells(line))
        idx += 1

    if not headers and not rows:
        return None, start
    return DocTable(caption="", headers=headers, rows=rows), idx


def structure_from_markdown(text: str) -> DocumentStructure | None:
    body = (text or "").strip()
    if len(body) < 40:
        return None

    lines = [ln.rstrip() for ln in body.replace("\r\n", "\n").split("\n")]
    title = ""
    sections: list[DocSection] = []
    tables: list[DocTable] = []
    current_heading = ""
    current_paras: list[str] = []
    i = 0

    def flush_section() -> None:
        nonlocal current_heading, current_paras
        if current_heading or current_paras:
            sections.append(
                DocSection(heading=current_heading, paragraphs=current_paras.copy())
            )
        current_heading = ""
        current_paras = []

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        table, next_i = _parse_table_block(lines, i)
        if table is not None:
            flush_section()
            tables.append(table)
            i = next_i
            continue

        if line.startswith("# "):
            flush_section()
            title = strip_inline_markdown(line[2:])[:300]
            i += 1
            continue

        if line.startswith("## "):
            flush_section()
            current_heading = strip_inline_markdown(line[3:])[:300]
            i += 1
            continue

        if line.startswith("### "):
            sub = strip_inline_markdown(line[4:])[:300]
            if sub:
                current_paras.append(sub)
            i += 1
            continue

        if line.startswith(("- ", "* ", "• ")):
            current_paras.append(f"• {strip_inline_markdown(line[2:])}"[:8000])
            i += 1
            continue

        if re.match(r"^\d+(?:\.\d+)*\.?\s+", line):
            current_paras.append(strip_inline_markdown(line)[:8000])
            i += 1
            continue

        plain = strip_inline_markdown(line)
        if plain:
            current_paras.append(plain[:8000])
        i += 1

    flush_section()

    if not title:
        if sections and sections[0].heading:
            title = sections[0].heading
        elif sections and sections[0].paragraphs:
            title = sections[0].paragraphs[0][:200]
        elif tables and tables[0].headers:
            title = tables[0].headers[0][:200]
        else:
            title = "Документ"

    if not sections and not tables:
        return structure_from_plain_text(body)

    total_paras = sum(len(s.paragraphs) for s in sections)
    if total_paras < 1 and not any(s.heading for s in sections) and not tables:
        return structure_from_plain_text(body)

    return DocumentStructure(title=title, sections=sections, tables=tables)


def resolve_export_structure(text: str) -> DocumentStructure | None:
    """Markdown → plain; без вызова LLM."""
    body = (text or "").strip()
    if len(body) < 40:
        return None
    looks_markdown = "#" in body[:500] or "```" in body or "|" in body
    if looks_markdown:
        cleaned = body
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        structure = structure_from_markdown(cleaned)
        if structure is not None:
            return structure
    return structure_from_plain_text(body)
