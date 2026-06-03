"""Сборка структуры Word из готового текста в чате (без «придумывания» нового документа)."""

from __future__ import annotations

import re

from app.services.doc_gen_schema import DocSection, DocumentStructure

# Строка-метка источника в ответе с веб-поиском (ooke, memoai).
_SOURCE_CHIP_LINE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,20}$")

_SECTION_NUM_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
_TITLE_LINE_RE = re.compile(
    r"(?i)^(?:публичн\w*\s+оферт|договор|соглашен|заявлен|политик\w*\s+конфиденциальности)",
)
_SECTION_TITLE_RE = re.compile(
    r"(?i)^(?:термины|предмет|порядок|права|стоимость|ответственность|персональн|реквизит|особые|заключительн)",
)


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            lines.append("")
            continue
        if _SOURCE_CHIP_LINE_RE.fullmatch(s):
            continue
        lines.append(s)
    return lines


def _is_heading(line: str, *, prev_blank: bool) -> bool:
    if re.match(r"^\d+\.\d+", line):
        return False
    if _SECTION_NUM_RE.match(line):
        return True
    if len(line) > 90:
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    if _TITLE_LINE_RE.search(line):
        return True
    if len(line) <= 80 and _SECTION_TITLE_RE.search(line):
        return True
    # Короткий заголовок раздела после пустой строки
    if prev_blank and line[0].isupper() and len(line.split()) <= 8:
        letters = sum(1 for c in line if c.isalpha())
        upper = sum(1 for c in line if c.isupper())
        if letters > 0 and upper / letters >= 0.5:
            return True
    return False


def structure_from_plain_text(text: str) -> DocumentStructure | None:
    """
    Разбивает готовый текст оферты/договора на разделы для docx.
    Возвращает None, если текст слишком короткий или не похож на документ.
    """
    body = (text or "").strip()
    if len(body) < 200:
        return None

    lines = _clean_lines(body)
    title = ""
    sections: list[DocSection] = []
    current_heading = ""
    current_paras: list[str] = []
    prev_blank = True

    def flush_section() -> None:
        nonlocal current_heading, current_paras
        if current_heading or current_paras:
            sections.append(
                DocSection(heading=current_heading, paragraphs=current_paras.copy())
            )
        current_heading = ""
        current_paras = []

    for line in lines:
        if not line:
            prev_blank = True
            continue

        if not title and _TITLE_LINE_RE.search(line):
            title = line[:300]
            prev_blank = False
            continue

        if _is_heading(line, prev_blank=prev_blank):
            flush_section()
            current_heading = line[:300]
            prev_blank = False
            continue

        if not title and not sections and not current_heading and not current_paras:
            title = line[:300]
            prev_blank = False
            continue

        current_paras.append(line[:8000])
        prev_blank = False

    flush_section()

    if not title:
        title = "Документ"
    if not sections:
        sections = [DocSection(heading="", paragraphs=[body[:12000]])]

    total_paras = sum(len(s.paragraphs) for s in sections)
    if total_paras < 1:
        return None

    return DocumentStructure(title=title, sections=sections, tables=[])
