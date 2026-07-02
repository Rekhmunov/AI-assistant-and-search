"""Пост-обработка ответа: документы в блоке ```markdown и правки черновика."""

from __future__ import annotations

import re

from app.services.doc_gen_routing import wants_document_generation

_MD_FENCE_RE = re.compile(r"```(?:markdown|md)\b", re.I)


def has_markdown_document_fence(text: str) -> bool:
    return bool(_MD_FENCE_RE.search(text or ""))


def document_request_prompt_addon(query: str, *, is_legal_doc: bool = False) -> str:
    if not wants_document_generation(query):
        return ""
    lines = [
        "\n\nДОПОЛНЕНИЕ К ЗАДАЧЕ — ГЕНЕРАЦИЯ ДОКУМЕНТА:",
        "Проанализируй актуальные законы из источников [n] для этого документа и сформируй итоговый документ в соответствии с ними.",
        "Руководствуйся официальными источниками: сайт налоговой (nalog.ru), КонсультантПлюс, Гарант и официальные реестры законодательства РФ.",
    ]
    return "\n".join(lines)


def edit_document_prompt_addon(query: str) -> str:
    q = (query or "").lower()
    hints = (
        "раздел", "документ", "оферт", "договор", "заявлен",
        "реквизит", "плейсхолдер", "диаграм", "график", "chart",
        "визуал", "вставь", "добавь",
    )
    if not any(h in q for h in hints):
        return ""
    return (
        "\n\nДополнение: правка документа из диалога.\n"
        "- Весь текст документа — в ОДНОМ блоке ```markdown … ``` (заголовки # / ##, нумерация).\n"
        "- Не разбивай документ на несколько блоков ```markdown … ```."
    )


def ensure_markdown_document_answer(answer: str, query: str) -> tuple[str, bool]:
    """
    Оборачивает длинный ответ в ```markdown, если запрос на документ, а модель не использовала блок.
    Возвращает (текст, changed).
    """
    body = (answer or "").strip()
    if not body or has_markdown_document_fence(body):
        return answer, False
    if not wants_document_generation(query):
        return answer, False
    if len(body) < 280:
        return answer, False

    looks_structured = bool(
        re.search(r"(?m)^#{1,3}\s+\S", body)
        or re.search(r"(?m)^\d+(?:\.\d+)*\.?\s+\S", body)
        or len(body) >= 900
    )
    if not looks_structured:
        return answer, False

    intro = "Ниже полный текст документа."
    wrapped = f"{intro}\n\n```markdown\n{body}\n```"
    return wrapped, True
