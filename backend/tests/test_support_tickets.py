import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.support_ticket import SupportTicketStatus
from app.services.support_tickets import create_support_ticket


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
    db.add.assert_called_once()
