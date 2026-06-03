"""Контекст треда для генерации Word: «из текста выше» и черновики в чате."""

from __future__ import annotations

import re

from app.models.message import Message, MessageRole

REFER_PRIOR_RE = re.compile(
    r"(?i)(?:"
    r"из\s+текста\s+выше|из\s+ответа\s+выше|по\s+тексту\s+выше|"
    r"на\s+основе\s+(?:текста|ответа|материала|выше)|"
    r"из\s+предыдущ|из\s+диалог|из\s+чата|"
    r"оформи\s+(?:в\s+)?(?:word|документ|docx)|"
    r"сгенерируй\s+документ|сделай\s+документ|в\s+виде\s+документа"
    r")",
)

# Лимит исходника из чата (символы), чтобы влезть в контекст LLM + JSON.
MAX_SOURCE_MATERIAL_CHARS = 14_000


def wants_prior_thread_material(query: str) -> bool:
    return bool(REFER_PRIOR_RE.search(query or ""))


def _assistant_contents(messages: list[Message], *, max_messages: int = 2) -> list[str]:
    bodies: list[str] = []
    for m in reversed(messages):
        if m.role != MessageRole.ASSISTANT:
            continue
        text = (m.content or "").strip()
        if not text:
            continue
        bodies.append(text)
        if len(bodies) >= max_messages:
            break
    return list(reversed(bodies))


def should_attach_prior_material(query: str, prior_messages: list[Message]) -> bool:
    if not prior_messages:
        return False
    if wants_prior_thread_material(query):
        return True
    last = _assistant_contents(prior_messages, max_messages=1)
    if not last or len(last[0]) < 600:
        return False
    q = (query or "").strip().lower()
    if len(q) > 120:
        return False
    hints = (
        "документ",
        "word",
        "docx",
        "оферт",
        "договор",
        "заявлен",
        "соглашен",
        "политик",
        "регламент",
        "отчет",
        "отчёт",
    )
    return any(h in q for h in hints)


def _trim_source(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_SOURCE_MATERIAL_CHARS:
        return text
    return text[:MAX_SOURCE_MATERIAL_CHARS] + "\n\n[…текст обрезан для лимита модели…]"


def build_doc_gen_user_message(query: str, prior_messages: list[Message]) -> str:
    """Текст user-сообщения для LLM: запрос + при необходимости черновик из чата."""
    q = (query or "").strip()
    if not should_attach_prior_material(q, prior_messages):
        return q

    parts = _assistant_contents(prior_messages, max_messages=2)
    if not parts:
        return q

    source = _trim_source("\n\n---\n\n".join(parts))
    return (
        f"Запрос пользователя: {q}\n\n"
        "Исходный материал из диалога (оформи как полноценный Word-документ: "
        "сохрани разделы, формулировки и нумерацию; не заменяй готовый текст "
        "на общие шаблоны):\n"
        f"---\n{source}\n---"
    )
