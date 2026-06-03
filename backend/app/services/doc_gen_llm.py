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
- Текст на русском, деловой стиль.
- Если в запросе есть блок «Исходный материал из диалога» — это основа документа: перенеси содержание в sections,
  сохрани структуру (разделы 1., 2., …), ключевые формулировки и списки. Не сжимай до 2–3 общих абзацев-заглушек.
- Не подменяй готовый текст шаблонами вида «[перечислить услуги]», «[название компании]», если в материале уже есть конкретика.
- Плейсхолдеры в квадратных скобках — только для реквизитов (ИНН, ОГРН, адрес, р/с), которых нет ни в запросе, ни в материале.
- Минимум один раздел с абзацами или одна таблица.
- Не дублируй в sections дисклеймер про юридическую консультацию — он добавляется в Word отдельно."""


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
