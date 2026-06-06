import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_current_user, get_db, get_redis
from app.core.request_security import verify_allowed_origin
from app.models.support_ticket import SupportTicketStatus
from app.models.user import User
from app.schemas.support import (
    SupportTicketCreate,
    SupportTicketCreateOut,
    SupportTicketReplyCreate,
    SupportTicketReplyOut,
    SupportTicketUserOut,
)
from app.services.support_tickets import (
    add_user_reply,
    create_support_ticket,
    get_ticket_for_user,
    list_tickets_for_user,
    mark_ticket_read_for_user,
    notify_admins_new_ticket,
    ticket_can_reply,
    ticket_has_unread_for_user,
)

import redis.asyncio as redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

_SUPPORT_UNAVAILABLE = "Сервис поддержки временно недоступен. Попробуйте позже."


def _ticket_status_value(status) -> str:
    if isinstance(status, SupportTicketStatus):
        return status.value
    return str(status)


def _ticket_user_out(ticket) -> SupportTicketUserOut:
    sorted_replies = sorted(ticket.replies, key=lambda r: r.created_at)
    return SupportTicketUserOut(
        id=ticket.id,
        source=ticket.source,
        message=ticket.message,
        status=_ticket_status_value(ticket.status),
        created_at=ticket.created_at,
        closed_at=ticket.closed_at,
        has_unread_reply=ticket_has_unread_for_user(ticket),
        can_reply=ticket_can_reply(ticket),
        replies=[
            SupportTicketReplyOut(
                id=r.id,
                author_type=r.author_type,
                admin_email=r.admin_email,
                message=r.message,
                created_at=r.created_at,
            )
            for r in sorted_replies
        ],
    )


@router.get("/tickets", response_model=list[SupportTicketUserOut])
async def list_my_support_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    tickets = await list_tickets_for_user(db, user.id)
    return [_ticket_user_out(t) for t in tickets]


@router.get("/tickets/{ticket_id}", response_model=SupportTicketUserOut)
async def get_my_support_ticket(
    ticket_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    ticket = await get_ticket_for_user(db, ticket_id, user.id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")
    return _ticket_user_out(ticket)


@router.post("/tickets", response_model=SupportTicketCreateOut, status_code=status.HTTP_201_CREATED)
async def create_support_ticket_endpoint(
    request: Request,
    body: SupportTicketCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    message = body.message.strip()
    if len(message) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите сообщение")

    source = (body.source or "general").strip()[:64] or "general"
    try:
        ticket = await create_support_ticket(
            db,
            redis_client,
            user=user,
            message=message,
            source=source,
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except StarletteHTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("support ticket create failed for user %s", user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SUPPORT_UNAVAILABLE,
        ) from exc

    try:
        await notify_admins_new_ticket(db, redis_client, ticket)
    except Exception:
        logger.exception("support admin notify failed for ticket %s", ticket.id)

    return SupportTicketCreateOut(
        id=ticket.id,
        created_at=ticket.created_at or datetime.now(timezone.utc),
    )


@router.post("/tickets/{ticket_id}/replies", response_model=SupportTicketUserOut)
async def reply_to_my_support_ticket(
    ticket_id: UUID,
    body: SupportTicketReplyCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    ticket = await get_ticket_for_user(db, ticket_id, user.id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")
    if not ticket_can_reply(ticket):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тикет закрыт")

    message = body.message.strip()
    if len(message) < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите сообщение")

    try:
        await add_user_reply(db, redis_client, ticket=ticket, user=user, message=message)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        logger.exception("support user reply failed ticket=%s user=%s", ticket_id, user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SUPPORT_UNAVAILABLE,
        ) from exc

    refreshed = await get_ticket_for_user(db, ticket_id, user.id)
    assert refreshed is not None
    return _ticket_user_out(refreshed)


@router.post("/tickets/{ticket_id}/read", response_model=SupportTicketUserOut)
async def mark_my_support_ticket_read(
    ticket_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    ticket = await get_ticket_for_user(db, ticket_id, user.id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")

    try:
        await mark_ticket_read_for_user(db, ticket)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("support mark read failed ticket=%s user=%s", ticket_id, user.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SUPPORT_UNAVAILABLE,
        ) from exc

    refreshed = await get_ticket_for_user(db, ticket_id, user.id)
    assert refreshed is not None
    return _ticket_user_out(refreshed)
