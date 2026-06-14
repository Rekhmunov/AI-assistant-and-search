"""
Компилятор правил секретаря: преобразует текстовую инструкцию в DSL-правила (JSON).
LLM вызывается ОДИН РАЗ для компиляции. Дальше агент работает детерминированно.
При неудаче — анализирует что неясно и возвращает первый уточняющий вопрос.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_COMPILER_PROMPT = """Ты — компилятор правил агента-секретаря. Твоя задача:
проанализировать инструкцию пользователя и создать ТОЧНЫЕ машиночитаемые правила в JSON.

Правила должны охватывать ВСЕ аспекты работы агента так, чтобы он мог работать
ПОЛНОСТЬЮ без LLM — только по этим правилам.

Верни ТОЛЬКО валидный JSON по следующей схеме (без markdown, без комментариев):

{
  "version": 1,
  "task_description": "краткое описание задачи агента",
  "input_patterns": [
    {
      "type": "amount_keyword",
      "description": "описание формата входного сообщения"
    }
  ],
  "entities": [
    {
      "name": "точное название сущности/категории",
      "triggers": ["ключевое слово 1", "синоним 2", "синоним 3"],
      "require_clarification": false,
      "clarification_options": [],
      "clarification_question": ""
    }
  ],
  "record_schema": {
    "fields": [
      {"name": "category", "type": "entity", "required": true},
      {"name": "amount", "type": "number", "required": true},
      {"name": "note", "type": "text", "required": false}
    ],
    "table": "records"
  },
  "responses": {
    "on_success": "✅ {amount} → {category}",
    "on_missing_amount": "сообщение когда нет суммы",
    "on_unknown_entity": "❓ Не распознана категория '{token}'. Уточните:",
    "on_multi_record": "✅ Записано {count} позиций"
  },
  "commands": {
    "report": {
      "triggers": ["отчёт", "пришли отчёт", "сформируй", "пришли excel", "excel"],
      "require_period": true,
      "period_question": "За какой период нужен отчёт?",
      "format": "xlsx",
      "columns": ["Категория", "Сумма", "Примечание"],
      "title_template": "Отчёт за {period}"
    },
    "show_records": {
      "triggers": ["покажи", "что записано", "покажи записи", "итого", "сколько"],
      "limit": 20
    },
    "delete": {
      "triggers": ["удали", "отмени запись", "убери", "удали последнюю"],
      "require_confirmation": true
    }
  }
}

ВАЖНО:
- triggers пиши строчными буквами
- Если у сущности есть уточняющие варианты (например "стежка белая/серая") — 
  добавь их в clarification_options и поставь require_clarification: true
- Если сущности/категории нет, но есть другой тип задачи — адаптируй схему
- Включи ВСЕ синонимы и варианты написания в triggers
- on_missing_amount: сообщение из инструкции если оно есть, иначе стандартное
"""


def _validate_rules(data: dict[str, Any]) -> bool:
    """Минимальная валидация структуры правил."""
    if not isinstance(data, dict):
        return False
    if data.get("version") != 1:
        return False
    if not isinstance(data.get("entities"), list):
        return False
    if not isinstance(data.get("commands"), dict):
        return False
    return True


_ANALYZER_PROMPT = """Ты — аналитик инструкций для агента-секретаря.
Инструкция для агента есть, но она неполная или неоднозначная.
Твоя задача — найти ВСЕ пункты которые нужно уточнить для создания чётких правил.

Выдай список вопросов в формате JSON:
{
  "unclear_aspects": [
    {"aspect": "что именно неясно", "question": "конкретный вопрос пользователю"}
  ],
  "first_question": "первый вопрос для уточнения (самый важный)"
}

Если что-то неясно — спроси. Не додумывай сам.
"""


async def analyze_instruction_gaps(llm, instruction: str) -> str:
    """
    Анализирует инструкцию и возвращает первый уточняющий вопрос.
    Вызывается когда compile_secretary_rules вернул None.
    """
    messages = [
        {"role": "system", "text": _ANALYZER_PROMPT},
        {"role": "user", "text": f"Инструкция:\n\n{instruction}"},
    ]
    try:
        raw = await llm.complete_text(messages, model="pro", max_tokens=1000, temperature=0.3)
        raw = (raw or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(raw)
        return data.get("first_question") or "Уточните подробнее что и как записывать."
    except Exception:
        return "Уточните: какой формат сообщений ожидается и какие категории/типы нужно различать?"


async def compile_secretary_rules(
    llm,
    instruction: str,
) -> dict[str, Any] | None:
    """
    Компилирует текстовую инструкцию в DSL-правила.
    Возвращает dict с правилами или None при ошибке.
    """
    if not instruction or not instruction.strip():
        return None

    messages = [
        {"role": "system", "text": _COMPILER_PROMPT},
        {"role": "user", "text": f"Инструкция для компиляции:\n\n{instruction}"},
    ]

    try:
        raw = await llm.complete_text(messages, model="pro", max_tokens=3000, temperature=0.2)
        raw = (raw or "").strip()

        # Убираем markdown если LLM обернул
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(raw)
        if not _validate_rules(data):
            logger.warning("Secretary compiler: invalid rules structure")
            return None

        logger.info(
            "Secretary rules compiled: entities=%s commands=%s",
            len(data.get("entities", [])),
            list(data.get("commands", {}).keys()),
        )
        return data

    except Exception as exc:
        logger.warning("Secretary compiler failed: %s", exc)
        return None
