"""Разбор markdown-блока ответа в структуру для экспорта Docx/PDF."""

from __future__ import annotations

import re

from app.services.doc_gen_plain import structure_from_plain_text
from app.services.doc_gen_schema import DocSection, DocumentStructure

_INLINE_MD_RE = re.compile(
    r"\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\([^)]+\)"
)


def strip_inline_markdown(text: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        return next(g for g in match.groups() if g is not None)

    return _INLINE_MD_RE.sub(_repl, text).strip()


def structure_from_markdown(text: str) -> DocumentStructure | None:
    body = (text or "").strip()
    if len(body) < 40:
        return None

    title = ""
    sections: list[DocSection] = []
    current_heading = ""
    current_paras: list[str] = []

    def flush_section() -> None:
        nonlocal current_heading, current_paras
        if current_heading or current_paras:
            sections.append(
                DocSection(heading=current_heading, paragraphs=current_paras.copy())
            )
        current_heading = ""
        current_paras = []

    for raw in body.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue

        if line.startswith("# "):
            flush_section()
            title = strip_inline_markdown(line[2:])[:300]
            continue

        if line.startswith("## "):
            flush_section()
            current_heading = strip_inline_markdown(line[3:])[:300]
            continue

        if line.startswith("### "):
            sub = strip_inline_markdown(line[4:])[:300]
            if sub:
                current_paras.append(sub)
            continue

        if line.startswith(("- ", "* ", "• ")):
            current_paras.append(f"• {strip_inline_markdown(line[2:])}"[:8000])
            continue

        if re.match(r"^\d+\.\s+", line):
            current_paras.append(strip_inline_markdown(line)[:8000])
            continue

        plain = strip_inline_markdown(line)
        if plain:
            current_paras.append(plain[:8000])

    flush_section()

    if not title:
        if sections and sections[0].heading:
            title = sections[0].heading
        elif sections and sections[0].paragraphs:
            title = sections[0].paragraphs[0][:200]
        else:
            title = "Документ"

    if not sections:
        return structure_from_plain_text(body)

    total_paras = sum(len(s.paragraphs) for s in sections)
    if total_paras < 1 and not any(s.heading for s in sections):
        return structure_from_plain_text(body)

    return DocumentStructure(title=title, sections=sections, tables=[])


def resolve_export_structure(text: str) -> DocumentStructure | None:
    """Markdown → plain; без вызова LLM."""
    body = (text or "").strip()
    if len(body) < 40:
        return None
    looks_markdown = "#" in body[:500] or "```" in body
    if looks_markdown:
        cleaned = body
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.I)
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)
        structure = structure_from_markdown(cleaned)
        if structure is not None:
            return structure
    return structure_from_plain_text(body)
