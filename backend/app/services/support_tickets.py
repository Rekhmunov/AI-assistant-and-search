"""Тикеты поддержки: создание, уведомления, привязка платежа."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.admin_user import AdminUser
from app.models.subscription import Subscription
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.support_ticket_reply import SupportTicketReply
from app.models.user import User
from app.services.app_settings import get_setting
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

SUPPORT_RATE_WINDOW_SEC = 86400
SUPPORT_RATE_MAX_PER_DAY = 5


async def check_support_rate_limit(redis_client: redis.Redis, user_id: uuid.UUID) -> None:
    key = f"support_ticket_day:{user_id}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, SUPPORT_RATE_WINDOW_SEC)
    if count > SUPPORT_RATE_MAX_PER_DAY:
        raise ValueError("Слишком много обращений за сутки. Попробуйте позже.")


async def find_recent_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def attach_payment_context(
    db: AsyncSession,
    ticket: SupportTicket,
    user: User,
    *,
    source: str,
) -> None:
    if source != "pro_payment":
        return
    sub = await find_recent_subscription(db, user.id)
    if not sub:
        return
    ticket.subscription_id = sub.id
    ticket.yookassa_payment_id = sub.yookassa_payment_id
    ticket.payment_amount_rub = sub.amount_rub


def _parse_notify_max_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").replace(";", ",").split(","):
        piece = part.strip()
        if not piece:
            continue
        try:
            ids.append(int(piece))
        except ValueError:
            continue
    return ids


async def notify_admins_new_ticket(
    db: AsyncSession,
    redis_client: redis.Redis,
    ticket: SupportTicket,
) -> None:
    raw = str(await get_setting("support_notify_max_user_ids", db, redis_client) or "").strip()
    max_ids = _parse_notify_max_ids(raw)
    if not max_ids:
        return

    payment_hint = ""
    if ticket.yookassa_payment_id:
        amount = f"{ticket.payment_amount_rub} ₽" if ticket.payment_amount_rub else "—"
        payment_hint = f"\nПлатёж: {ticket.yookassa_payment_id} ({amount})"

    text = (
        f"Новый тикет поддержки ({ticket.source})\n"
        f"От: {ticket.user_email or 'без email'}"
        f"{f' · MAX {ticket.user_max_user_id}' if ticket.user_max_user_id else ''}\n"
        f"{ticket.message[:500]}{payment_hint}"
    )
    bot = MaxBotService()
    for max_user_id in max_ids:
        result = await bot.send_message(max_user_id, text)
        if not result.ok:
            logger.warning("support notify failed for max_user_id=%s: %s", max_user_id, result.error)


async def notify_user_ticket_reply(user: User, reply_text: str) -> None:
    if not user.max_user_id:
        return
    bot = MaxBotService()
    text = f"Ответ поддержки Glosix:\n\n{reply_text[:1500]}"
    result = await bot.send_message(user.max_user_id, text)
    if not result.ok:
        logger.warning("support user notify failed for user %s: %s", user.id, result.error)


async def create_support_ticket(
    db: AsyncSession,
    redis_client: redis.Redis,
    *,
    user: User,
    message: str,
    source: str,
) -> SupportTicket:
    await check_support_rate_limit(redis_client, user.id)
    ticket = SupportTicket(
        user_id=user.id,
        user_email=user.email,
        user_max_user_id=user.max_user_id,
        source=source,
        message=message,
        status=SupportTicketStatus.OPEN,
    )
    db.add(ticket)
    await db.flush()
    await attach_payment_context(db, ticket, user, source=source)
    await db.commit()
    await db.refresh(ticket)

    try:
        await notify_admins_new_ticket(db, redis_client, ticket)
    except Exception:
        logger.exception("support admin notify failed for ticket %s", ticket.id)

    return ticket


async def get_ticket_for_user(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SupportTicket | None:
    result = await db.execute(
        select(SupportTicket)
        .options(selectinload(SupportTicket.replies))
        .where(SupportTicket.id == ticket_id, SupportTicket.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_tickets_for_user(db: AsyncSession, user_id: uuid.UUID, *, limit: int = 20) -> list[SupportTicket]:
    result = await db.execute(
        select(SupportTicket)
        .options(selectinload(SupportTicket.replies))
        .where(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_ticket_admin(db: AsyncSession, ticket_id: uuid.UUID) -> SupportTicket | None:
    result = await db.execute(
        select(SupportTicket)
        .options(selectinload(SupportTicket.replies))
        .where(SupportTicket.id == ticket_id)
    )
    return result.scalar_one_or_none()


async def add_admin_reply(
    db: AsyncSession,
    *,
    ticket: SupportTicket,
    admin: AdminUser,
    message: str,
) -> SupportTicketReply:
    reply = SupportTicketReply(
        ticket_id=ticket.id,
        author_type="admin",
        admin_id=admin.id,
        admin_email=admin.email,
        message=message,
    )
    db.add(reply)
    if ticket.status == SupportTicketStatus.OPEN:
        ticket.status = SupportTicketStatus.IN_PROGRESS
    await db.flush()

    user_result = await db.execute(select(User).where(User.id == ticket.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        try:
            await notify_user_ticket_reply(user, message)
        except Exception:
            logger.exception("support user reply notify failed ticket=%s", ticket.id)

    await db.flush()
    return reply


async def set_ticket_status(
    db: AsyncSession,
    ticket: SupportTicket,
    status: SupportTicketStatus,
    *,
    admin: AdminUser | None = None,
) -> SupportTicket:
    ticket.status = status
    if status == SupportTicketStatus.CLOSED:
        ticket.closed_at = datetime.now(timezone.utc)
        ticket.closed_by_admin_id = admin.id if admin else ticket.closed_by_admin_id
    elif status in (SupportTicketStatus.OPEN, SupportTicketStatus.IN_PROGRESS):
        ticket.closed_at = None
        ticket.closed_by_admin_id = None
    await db.flush()
    return ticket
