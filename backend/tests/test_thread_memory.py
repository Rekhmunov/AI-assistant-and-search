"""Тесты thread_memory и agent_records."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncio

from app.models.agent import AgentInstance, AgentStatus
from app.models.message import Message, MessageRole
from app.services.agent.agent_records import query_records, store_record
from app.services.agent.thread_memory import _score_text, _tokenize, search_thread_history


def _agent(**kwargs) -> AgentInstance:
    defaults = {
        "id": uuid.uuid4(),
        "thread_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "max_user_id": 1,
        "status": AgentStatus.ACTIVE.value,
        "config": {},
        "instruction_text": "",
    }
    defaults.update(kwargs)
    return AgentInstance(**defaults)


def test_tokenize_and_score():
    tokens = _tokenize("затраты аренда excel")
    assert "затраты" in tokens
    assert _score_text("запись про затраты и аренда офиса", tokens) >= 4


def test_store_and_query_records():
    agent = _agent()
    store_record(
        agent,
        "expenses",
        {"category": "Аренда", "amount": 1500, "description": "интернет"},
        author="user1",
        chat_id=-100,
    )
    rows = query_records(agent, "expenses", category="Аренда")
    assert len(rows) == 1
    assert rows[0]["amount"] == 1500
    assert rows[0]["author"] == "user1"


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeDb:
    def __init__(self, messages):
        self._messages = messages

    async def execute(self, _stmt):
        return _FakeResult(self._messages)


def test_search_thread_history_matches_query():
    thread_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    messages = [
        Message(
            thread_id=thread_id,
            role=MessageRole.USER,
            content="буду писать затраты аренда интернет",
            created_at=now,
        ),
        Message(
            thread_id=thread_id,
            role=MessageRole.ASSISTANT,
            content="понял, фиксирую в таблицу",
            created_at=now,
        ),
    ]
    db = _FakeDb(messages)
    items = asyncio.run(search_thread_history(db, thread_id, "аренда затраты"))
    assert len(items) >= 1
    assert any("аренда" in i["content"].lower() for i in items)
