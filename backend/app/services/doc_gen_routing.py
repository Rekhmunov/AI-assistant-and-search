"""Детектор запросов на генерацию Word-документа (не разбор загруженного файла)."""

from __future__ import annotations

import re

_DOC_GEN_RE = re.compile(
    r"(?i)(?:"
    r"составь|составить|оформи|оформить|подготовь|подготовить|"
    r"сгенерируй|сгенерировать|сделай|сделать|напиши|написать|"
    r"сформируй|сформировать|создай|создать|заполни|заполнить"
    r")"
    r"(?:\s+(?:мне|пожалуйста))?\s+"
    r"(?:"
    r"договор|заявлен|акт|доверенност|соглашен|приказ|"
    r"справк|резюме|отчёт|отчет|письм|претензи|иск|"
    r"документ|docx|word|ворд"
    r")",
)

_DOC_GEN_SHORT_RE = re.compile(
    r"(?i)^(?:"
    r"(?:договор|заявлен|акт|документ)\s*[:—-]\s*.+"
    r"|(?:сделай|составь|оформи)\s+(?:договор|заявлен|документ).+"
    r")$",
)

_PDF_EXPLICIT_RE = re.compile(r"(?i)\b(?:в\s+)?pdf\b")


def wants_document_generation(query: str) -> bool:
    text = (query or "").strip()
    if len(text) < 6:
        return False
    if _DOC_GEN_SHORT_RE.match(text):
        return True
    return bool(_DOC_GEN_RE.search(text))


def resolve_output_format(query: str) -> str:
    """Пока только docx; pdf — позже из того же JSON."""
    if _PDF_EXPLICIT_RE.search(query or ""):
        return "pdf"
    return "docx"
