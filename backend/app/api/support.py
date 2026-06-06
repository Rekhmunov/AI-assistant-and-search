from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.request_security import verify_allowed_origin
from app.models.user import User
from app.schemas.support import (
    SupportTicketCreate,
    SupportTicketCreateOut,
    SupportTicketReplyOut,
    SupportTicketUserOut,
)
from app.services.support_tickets import create_support_ticket, get_ticket_for_user, list_tickets_for_user

import redis.asyncio as redis

router = APIRouter(prefix="/support", tags=["support"])


def _ticket_user_out(ticket) -> SupportTicketUserOut:
    return SupportTicketUserOut(
        id=ticket.id,
        source=ticket.source,
        message=ticket.message,
        status=ticket.status.value,
        created_at=ticket.created_at,
        closed_at=ticket.closed_at,
        replies=[
            SupportTicketReplyOut(
                id=r.id,
                author_type=r.author_type,
                admin_email=r.admin_email,
                message=r.message,
                created_at=r.created_at,
            )
            for r in ticket.replies
            if r.author_type == "admin"
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    return SupportTicketCreateOut(id=ticket.id, created_at=ticket.created_at)
