"""Запрос к LLM: структура документа в JSON."""

from __future__ import annotations

import logging

from app.services.doc_gen_schema import DocumentStructure, DocumentStructureError, parse_document_structure
from app.services.providers.factory import ChatLLM

logger = logging.getLogger(__name__)

DOC_GEN_SYSTEM = """Ты помощник, который готовит структуру официального документа для экспорта в Word.
Ответь ТОЛЬКО валидным JSON без markdown и комментариев.

Схема:
{
  "title": "заголовок документа",
  "sections": [
    {"heading": "название раздела или пустая строка", "paragraphs": ["абзац 1", "абзац 2"]}
  ],
  "tables": [
    {"caption": "подпись таблицы или пусто", "headers": ["кол1", "кол2"], "rows": [["a", "b"]]}
  ]
}

Правила:
- Текст на русском, деловой стиль, по запросу пользователя.
- Не выдумывай конкретные ФИО, адреса, суммы, если пользователь их не дал — используй нейтральные плейсхолдеры в квадратных скобках.
- Минимум один раздел с абзацами или одна таблица.
- Без юридических гарантий в тексте — это черновик."""


async def generate_document_structure(
    llm: ChatLLM,
    user_query: str,
    *,
    answer_model: str,
) -> DocumentStructure:
    messages = [
        {"role": "system", "text": DOC_GEN_SYSTEM},
        {"role": "user", "text": user_query.strip()},
    ]
    raw = await llm.complete_text(
        messages,
        model="pro" if answer_model == "pro" else "lite",
        max_tokens=4096,
        temperature=0.3,
    )
    try:
        return parse_document_structure(raw)
    except DocumentStructureError:
        logger.warning("doc gen JSON parse failed, retrying with strict hint")
        retry_messages = messages + [
            {
                "role": "user",
                "text": "Верни только JSON по схеме из инструкции. Без ``` и без пояснений.",
            },
        ]
        raw2 = await llm.complete_text(
            retry_messages,
            model="pro" if answer_model == "pro" else "lite",
            max_tokens=4096,
            temperature=0.2,
        )
        return parse_document_structure(raw2)
