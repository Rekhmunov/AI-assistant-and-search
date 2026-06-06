import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.api.threads import get_thread_answer_status
from app.models.message import MessageRole
from app.services.search_pending import STALE_AFTER_SEC


def _msg(role, content: str, *, age_sec: int = 0):
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.role = role
    msg.content = content
    msg.created_at = datetime.now(timezone.utc) - timedelta(seconds=age_sec)
    return msg


def test_answer_status_stale_orphan_user_message():
    thread_id = uuid.uuid4()
    user = MagicMock()
    user.id = uuid.uuid4()

    thread = MagicMock()
    thread.id = thread_id
    thread.messages = [_msg(MessageRole.USER, "вопрос без ответа", age_sec=STALE_AFTER_SEC + 5)]

    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=thread),
        ),
    )

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    actor = MagicMock()
    actor.user = user

    out = asyncio.run(get_thread_answer_status(thread_id, db, actor, redis))
    assert out.pending is True
    assert out.active is False
    assert out.stale is True
    assert out.query == "вопрос без ответа"
