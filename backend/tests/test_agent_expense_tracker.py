"""Тесты учёта затрат в группе."""

from __future__ import annotations

from app.models.agent import AgentRole
from app.services.agent.expense_tracker import (
    apply_expense_tracker_checklist,
    extract_expense_categories,
    is_structured_group_tracker_task,
    parse_expense_line,
)
from app.services.agent.intent_hints import infer_role_from_text

USER_TASK = """
Я в эту группу буду писать затраты в формате
Сумма + описание.
Тебе нужно будет фиксировать эту сумму в таблицу, а по описанию определять категорию. Всего категорий столько:
Аренда (аренда, комуналка, вывоз мусора, интернет и пр.)
Борта (раздублировка бортов, нарезка бортов)
Заработная плата
Логистика (такси, поддоны, доставка до складов и пр.)
Прочие затраты

В таблице должно быть 3 столбца:
1) Категория
2) Сумма без пробелов, просто цифры
3) Описание

По запросу нужно будет присылать отчет в формате exel в которой будут затраты за нужный период.
"""


def test_structured_tracker_detected():
    assert is_structured_group_tracker_task(USER_TASK)


def test_not_group_reminder_for_expense_task():
    assert infer_role_from_text(USER_TASK) == AgentRole.DM_ASSISTANT.value


def test_expense_tracker_checklist_via_dedicated_function():
    """apply_expense_tracker_checklist заполняет специфические поля."""
    data = apply_expense_tracker_checklist({}, USER_TASK)
    assert data.get("task_mode") == "expense_tracker"
    assert data.get("output_format") == "xlsx"
    assert len(data.get("expense_categories") or []) >= 4


def test_parse_expense_line():
    result = parse_expense_line("5000 аренда офиса")
    assert result is not None
    amount, description = result
    assert amount == 5000
    assert "аренда" in description.lower()


def test_extract_expense_categories():
    cats = extract_expense_categories(USER_TASK)
    assert len(cats) >= 4
    assert any("аренда" in c.lower() for c in cats)
