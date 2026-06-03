"""Детектор запросов на генерацию Word (.docx).

Оферта, договор, заявление и т.п. по умолчанию — ответ в чате.
Файл Word — только при явном запросе документа (слово «документ», docx/word,
«в документ», «преобразуй в документ»).
"""

from __future__ import annotations

import re

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
    "преобразуй",
    "преобразовать",
    "конвертируй",
    "конвертировать",
    "экспортируй",
    "экспортировать",
    "переведи",
    "перевести",
    "сохрани",
    "сохранить",
)

_VERBS_PATTERN = "|".join(re.escape(v) for v in _DOC_GEN_VERBS)

# Явно просят текст в чате, не файл.
_IN_CHAT_RE = re.compile(
    r"(?i)(?:"
    r"\bв\s+чат(?:е)?\b"
    r"|\bв\s+ответ(?:е)?\b"
    r"|\bтекстом\b"
    r"|\bбез\s+(?:файл|документ)"
    r"|\bне\s+(?:делай|создавай|генерируй)?\s*(?:файл|документ)"
    r")",
)

# преобразуй / экспортируй … в документ|word|docx
_CONVERT_TO_DOC_RE = re.compile(
    rf"(?i)(?:{_VERBS_PATTERN})"
    r"(?:\s+\S+){{0,8}}?"
    r"\b(?:в\s+)?(?:документ|docx|word|ворд)\b",
)

# сгенерируй документ / создай docx (+ тема после: «документ оферту»)
_ACTION_DOCUMENT_RE = re.compile(
    rf"(?i)(?:{_VERBS_PATTERN})"
    r"(?:\s+(?:мне|пожалуйста))?"
    r"\s+(?:документ|docx|word|ворд)\b",
)

# оферту в документ / заявление в word / … как документ
_INTO_DOCUMENT_RE = re.compile(
    r"(?i)\b(?:в|как)\s+(?:файл\s+)?(?:документ|docx|word|ворд)\b",
)

# документ: текст заявления …
_DOC_COLON_SHORT_RE = re.compile(
    r"(?i)^(?:документ|docx|word|ворд)\s*[:—-]\s*.+",
)

_PDF_EXPLICIT_RE = re.compile(r"(?i)\b(?:в\s+)?pdf\b")


def wants_document_generation(query: str) -> bool:
    text = (query or "").strip()
    if len(text) < 6:
        return False
    if _IN_CHAT_RE.search(text):
        return False
    if _DOC_COLON_SHORT_RE.match(text):
        return True
    if _CONVERT_TO_DOC_RE.search(text):
        return True
    if _ACTION_DOCUMENT_RE.search(text):
        return True
    if _INTO_DOCUMENT_RE.search(text):
        return True
    return False


def resolve_output_format(query: str) -> str:
    """Пока только docx; pdf — позже из того же JSON."""
    if _PDF_EXPLICIT_RE.search(query or ""):
        return "pdf"
    return "docx"
