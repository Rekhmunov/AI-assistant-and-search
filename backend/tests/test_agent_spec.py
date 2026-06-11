"""Тесты agent_spec и capability registry."""

from __future__ import annotations

import uuid

from app.models.agent import AgentInstance, AgentStatus
from app.services.agent.agent_spec import (
    AgentSpec,
    load_agent_spec,
    save_agent_spec,
    spec_context_block,
    sync_spec_from_checklist,
)
from app.services.agent.max_capabilities import CAPABILITIES, tools_appendix_for_mode


def _agent(**kwargs) -> AgentInstance:
    defaults = {
        "id": uuid.uuid4(),
        "thread_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "max_user_id": 1,
        "status": AgentStatus.COLLECTING.value,
        "config": {},
        "instruction_text": "",
    }
    defaults.update(kwargs)
    return AgentInstance(**defaults)


def test_sync_spec_from_checklist_expense_tracker():
    agent = _agent()
    checklist = {
        "role": "dm_assistant",
        "task_mode": "expense_tracker",
        "expense_categories": ["Аренда", "Логистика"],
        "support_instructions": "Фиксируй затраты в таблицу",
        "output_format": "xlsx",
        "max_chat_id": -100,
    }
    spec = sync_spec_from_checklist(agent, checklist, user_text="учёт затрат в группе")
    assert spec.task_mode == "expense_tracker"
    assert "Аренда" in spec.categories
    assert spec.output_format == "xlsx"
    assert any("Группа MAX" in f for f in spec.facts)
    reloaded = load_agent_spec(agent)
    assert reloaded.task_mode == "expense_tracker"


def test_spec_context_includes_thread_memory():
    spec = AgentSpec(goal="Учёт затрат", thread_memory="Категории: Аренда, Логистика")
    block = spec_context_block(spec)
    assert "goal:" in block
    assert "thread_memory:" in block
    assert "Аренда" in block


def test_capabilities_registry_has_memory_tools():
    tools = {c.tool for c in CAPABILITIES}
    assert "search_thread_history" in tools
    assert "store_agent_record" in tools
    assert "update_agent_memory" in tools


def test_tools_appendix_runtime_mode():
    appendix = tools_appendix_for_mode(runtime=True)
    assert "store_agent_record" in appendix
    assert '"checklist"' not in appendix


def test_save_and_load_roundtrip():
    agent = _agent()
    spec = AgentSpec(goal="test", facts=["fact1"])
    save_agent_spec(agent, spec)
    loaded = load_agent_spec(agent)
    assert loaded.goal == "test"
    assert loaded.facts == ["fact1"]
