import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.support_ticket import SupportTicketStatus
from datetime import datetime, timedelta, timezone

from app.services.support_tickets import (
    create_support_ticket,
    ticket_has_unread_for_user,
    ticket_can_reply,
)


@pytest.mark.asyncio
async def test_create_support_ticket_uses_string_status_value():
    user_id = uuid.uuid4()
    user = MagicMock()
    user.id = user_id
    user.email = "user@example.com"
    user.max_user_id = 12345

    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    redis_client = MagicMock()
    redis_client.incr = AsyncMock(return_value=1)
    redis_client.expire = AsyncMock()

    ticket = await create_support_ticket(
        db,
        redis_client,
        user=user,
        message="Нужна помощь",
        source="general",
    )

    assert ticket.status == SupportTicketStatus.OPEN.value
    assert ticket.message == "Нужна помощь"
    assert ticket.user_last_read_at is not None
    db.add.assert_called_once()


def _reply(author_type: str, *, age_minutes: int = 0):
    reply = MagicMock()
    reply.author_type = author_type
    reply.created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return reply


def test_ticket_has_unread_when_admin_replied_after_read():
    ticket = MagicMock()
    ticket.user_last_read_at = datetime.now(timezone.utc) - timedelta(hours=1)
    ticket.replies = [_reply("admin", age_minutes=5)]
    assert ticket_has_unread_for_user(ticket) is True


def test_ticket_not_unread_when_user_read_latest_admin_reply():
    now = datetime.now(timezone.utc)
    ticket = MagicMock()
    ticket.user_last_read_at = now
    reply = _reply("admin")
    reply.created_at = now - timedelta(minutes=1)
    ticket.replies = [reply]
    assert ticket_has_unread_for_user(ticket) is False


def test_ticket_can_reply_false_when_closed():
    ticket = MagicMock()
    ticket.status = SupportTicketStatus.CLOSED.value
    assert ticket_can_reply(ticket) is False
