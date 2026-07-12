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

_COMPILER_PROMPT = """Ты — компилятор правил агента «Учет затрат». Твоя задача:
проанализировать список категорий затрат и создать машиночитаемые правила в JSON.

Правила должны охватывать ВСЕ аспекты работы агента так, чтобы он мог работать
ПОЛНОСТЬЮ без LLM — только по этим правилам.

Верни ТОЛЬКО валидный JSON по следующей схеме (без markdown, без комментариев):

{
  "version": 1,
  "task_description": "Учет затрат: записывает расходы из группы в формате сумма+примечание",
  "input_patterns": [
    {
      "type": "amount_keyword",
      "description": "число + текст или текст + число, например: 1500 доставка или ПЗР 3000"
    }
  ],
  "entities": [
    {
      "name": "точное название категории как в инструкции",
      "triggers": ["ключевое слово 1", "синоним 2", "сокращение"],
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
    "on_success": "✅ Записано в категорию: {category}",
    "on_missing_amount": "Для корректной записи нужно указать сумму и категорию затраты",
    "on_unknown_entity": "❓ К какой категории отнести «{token}»?",
    "on_multi_record": "✅ Записано {count} позиций"
  },
  "commands": {
    "report": {
      "triggers": ["отчёт", "пришли отчёт", "сформируй", "пришли excel", "excel", "пришли отчет", "генерируй отчет", "сгенерируй отчет"],
      "require_period": true,
      "period_question": "За какой период нужен отчёт? Укажите дату или диапазон (например: 14.06.2026 или с 01.06 по 14.06)",
      "format": "xlsx",
      "columns": ["Категория", "Затрата", "Примечание"],
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
- Для каждой категории добавляй очевидные сокращения и синонимы в triggers
  (например, для "Заработная плата" — ["зарплата", "зп", "заработная плата"])
- Если у категории есть варианты в скобках в названии — используй их как triggers
  (например, "Аренда (аренда, коммуналка)" → triggers: ["аренда", "коммуналка", "вывоз мусора"])
- name категории — точно как в списке пользователя (включая скобки)
- on_missing_amount и on_success — используй ТОЧНО как в шаблоне выше
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


_SELF_CORRECT_PROMPT = """Ты — компилятор правил агента-секретаря. Первая попытка компиляции не удалась.

Проанализируй инструкцию. Сделай следующее:
1. Найди что именно помешало создать правила (неоднозначность, противоречие, нехватка данных)
2. Если можешь ДОДУМАТЬ/ПРЕДПОЛОЖИТЬ недостающее из контекста — сделай это и скомпилируй правила
3. Если информации объективно не хватает (нет ни одной подсказки в тексте) — верни вопрос

Ответ СТРОГО в JSON:
{
  "can_fix": true/false,
  "fixed_rules": { ...полные правила по той же схеме если can_fix=true... },
  "missing_info": "что конкретно не хватает если can_fix=false",
  "question_for_user": "один конкретный вопрос если can_fix=false"
}
"""

_SCHEMA_REMINDER = """Схема правил:
{
  "version": 1, "task_description": "Учет затрат: записывает расходы из группы в формате сумма+примечание",
  "input_patterns": [{"type": "amount_keyword", "description": "число + текст или текст + число"}],
  "entities": [{"name": "...", "triggers": ["..."], "require_clarification": false, "clarification_options": [], "clarification_question": ""}],
  "record_schema": {"fields": [{"name": "category","type":"entity","required":true},{"name":"amount","type":"number","required":true},{"name":"note","type":"text","required":false}], "table": "records"},
  "responses": {"on_success":"✅ Записано в категорию: {category}","on_missing_amount":"Для корректной записи нужно указать сумму и категорию затраты","on_unknown_entity":"❓ К какой категории отнести «{token}»?","on_multi_record":"✅ Записано {count} позиций"},
  "commands": {"report":{"triggers":["отчёт","пришли отчёт","пришли excel","excel","генерируй отчет","сгенерируй отчет"],"require_period":true,"period_question":"За какой период нужен отчёт? Укажите дату или диапазон (например: 14.06.2026 или с 01.06 по 14.06)","format":"xlsx","columns":["Категория","Затрата","Примечание"],"title_template":"Отчёт за {period}"},"show_records":{"triggers":["покажи","что записано","покажи записи","итого","сколько"],"limit":20},"delete":{"triggers":["удали","отмени запись","убери","удали последнюю"],"require_confirmation":true}}
}"""


async def analyze_instruction_gaps(llm, instruction: str) -> tuple[dict | None, str]:
    """
    Пытается самостоятельно исправить инструкцию и скомпилировать правила.
    Возвращает (compiled_rules, question_for_user).
    - Если исправил сам → (rules, "")
    - Если нужен юзер → (None, "вопрос")
    """
    messages = [
        {"role": "system", "text": _SELF_CORRECT_PROMPT + "\n\n" + _SCHEMA_REMINDER},
        {"role": "user", "text": f"Инструкция:\n\n{instruction}"},
    ]
    try:
        raw = await llm.complete_text(messages, model="pro", max_tokens=6000, temperature=0.2)
        raw = (raw or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(raw)

        if data.get("can_fix") and isinstance(data.get("fixed_rules"), dict):
            rules = data["fixed_rules"]
            if _validate_rules(rules):
                logger.info("Secretary compiler self-corrected successfully")
                return rules, ""

        question = data.get("question_for_user") or "Уточните: какой формат сообщений и какие категории нужно различать?"
        return None, question

    except Exception as exc:
        logger.warning("Secretary self-correct failed: %s | raw=%s", exc, locals().get("raw", "")[:300])
        return None, "Уточните: какой формат сообщений ожидается и какие категории/типы нужно различать?"


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
        raw = await llm.complete_text(messages, model="pro", max_tokens=6000, temperature=0.2)
        raw = (raw or "").strip()
        logger.debug("secretary compiler raw first 300: %s", raw[:300])

        # Убираем markdown если LLM обернул
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        # Ищем JSON-блок если ответ содержит текст вокруг
        if not raw.startswith("{"):
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

        data = json.loads(raw)
        if not _validate_rules(data):
            logger.warning("COMPILER invalid structure: keys=%s version=%s", list(data.keys()), data.get("version"))
            return None

        logger.info(
            "Secretary rules compiled: entities=%s commands=%s",
            len(data.get("entities", [])),
            list(data.get("commands", {}).keys()),
        )
        return data

    except Exception as exc:
        logger.warning("Secretary compiler failed: %s | raw=%s", exc, locals().get("raw", "")[:300])
        return None
