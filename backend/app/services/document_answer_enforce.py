"""Пост-обработка ответа: документы в блоке ```markdown и правки черновика."""

from __future__ import annotations

import re

from app.services.doc_gen_routing import wants_document_generation

_MD_FENCE_RE = re.compile(r"```(?:markdown|md)\b", re.I)
_LEGAL_DOC_RE = re.compile(
    r"(?i)(?:оферт|договор|соглашен|заявлен|политик|регламент|устав|приказ)",
)


def has_markdown_document_fence(text: str) -> bool:
    return bool(_MD_FENCE_RE.search(text or ""))


def is_legal_document_request(query: str) -> bool:
    return bool(_LEGAL_DOC_RE.search(query or ""))


def document_request_prompt_addon(query: str) -> str:
    if not wants_document_generation(query):
        return ""
    legal = is_legal_document_request(query)
    lines = [
        "\n\nДополнение к задаче:",
        "Пользователь просит документ. Весь готовый текст документа помести в ОДИН блок ```markdown … ``` "
        "с заголовками # и ## внутри блока. Вне блока — только короткое вступление (1–2 предложения).",
        "Не сокращай юридические и деловые формулировки до общих фраз.",
    ]
    if legal:
        lines.append(
            "Это юридический/деловой шаблон для РФ: используй нейтральные плейсхолдеры "
            "[НАЗВАНИЕ КОМПАНИИ], [ИНН], [АДРЕС] там, где нужны реквизиты."
        )
    return "\n".join(lines)


def edit_document_prompt_addon(query: str) -> str:
    q = (query or "").lower()
    hints = (
        "раздел",
        "документ",
        "оферт",
        "договор",
        "заявлен",
        "реквизит",
        "плейсхолдер",
        "диаграм",
        "график",
        "chart",
        "визуал",
        "вставь",
        "добавь",
    )
    if not any(h in q for h in hints):
        return ""
    return (
        "\n\nДополнение: правка документа из диалога.\n"
        "- Весь текст документа — в ОДНОМ блоке ```markdown … ``` (заголовки # / ##, нумерация).\n"
        "- Если нужна диаграмма — сразу ПОСЛЕ закрывающих ``` markdown добавь один блок ```chart "
        "с JSON GlosixChart (не внутри markdown, не вторым markdown-блоком после chart).\n"
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
