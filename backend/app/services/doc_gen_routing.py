"""Детектор запросов на генерацию Word-документа (не разбор загруженного файла)."""

from __future__ import annotations

import re

# Только вместе с глаголом «создай / сгенерируй / …» — не срабатывает на «что такое оферта».
_DOC_GEN_VERBS = (
    "составь",
    "составить",
    "оформи",
    "оформить",
    "подготовь",
    "подготовить",
    "сгенерируй",
    "сгенерировать",
    "сделай",
    "сделать",
    "напиши",
    "написать",
    "сформируй",
    "сформировать",
    "создай",
    "создать",
    "заполни",
    "заполнить",
    "разработай",
    "разработать",
    "выгрузи",
    "выгрузить",
)

# Стебли слов — покрывают падежи и числа (оферта, оферту, соглашение, …).
_DOC_GEN_TYPES = (
    "договор",
    "контракт",
    "заявлен",
    "акт",
    "доверенност",
    "соглашен",
    "оферт",
    "меморанд",
    "устав",
    "положен",
    "регламент",
    "инструкци",
    "приказ",
    "распоряжен",
    "протокол",
    "справк",
    "резюме",
    "отчёт",
    "отчет",
    "письм",
    "служебн",
    "пояснительн",
    "претензи",
    "иск",
    "политик",
    "согласие",
    "лицензион",
    "коммерческ",
    "документ",
    "docx",
    "word",
    "ворд",
)

_VERBS_PATTERN = "|".join(re.escape(v) for v in _DOC_GEN_VERBS)
_TYPES_PATTERN = "|".join(_DOC_GEN_TYPES)

_DOC_GEN_RE = re.compile(
    rf"(?i)(?:{_VERBS_PATTERN})"
    r"(?:\s+(?:мне|пожалуйста))?(?:\s+\S+){0,6}?\s+"
    rf"(?:{_TYPES_PATTERN})",
)

_DOC_GEN_SHORT_RE = re.compile(
    rf"(?i)^(?:"
    rf"(?:{_TYPES_PATTERN})\s*[:—-]\s*.+"
    rf"|(?:сделай|составь|оформи|создай|сгенерируй)\s+(?:{_TYPES_PATTERN}).+"
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
