from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.schemas.support import (
    SupportTicketAdminOut,
    SupportTicketReplyCreate,
    SupportTicketReplyOut,
    SupportTicketStatusUpdate,
)
from app.services.admin_audit import log_admin_action
from app.services.support_tickets import add_admin_reply, get_ticket_admin, set_ticket_status

router = APIRouter(prefix="/support", tags=["admin-support"])


def _ticket_out(ticket: SupportTicket) -> SupportTicketAdminOut:
    return SupportTicketAdminOut(
        id=ticket.id,
        user_id=ticket.user_id,
        user_email=ticket.user_email,
        user_max_user_id=ticket.user_max_user_id,
        source=ticket.source,
        message=ticket.message,
        status=ticket.status.value,
        created_at=ticket.created_at,
        closed_at=ticket.closed_at,
        yookassa_payment_id=ticket.yookassa_payment_id,
        payment_amount_rub=ticket.payment_amount_rub,
        subscription_id=ticket.subscription_id,
        replies=[
            SupportTicketReplyOut(
                id=r.id,
                author_type=r.author_type,
                admin_email=r.admin_email,
                message=r.message,
                created_at=r.created_at,
            )
            for r in ticket.replies
        ],
    )


@router.get("/tickets", response_model=list[SupportTicketAdminOut])
async def list_support_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("support:read")),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    query = (
        select(SupportTicket)
        .options(selectinload(SupportTicket.replies))
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    if status_filter in ("open", "in_progress", "closed"):
        query = query.where(SupportTicket.status == SupportTicketStatus(status_filter))
    elif status_filter == "active":
        query = query.where(
            SupportTicket.status.in_([SupportTicketStatus.OPEN, SupportTicketStatus.IN_PROGRESS])
        )
    result = await db.execute(query)
    return [_ticket_out(t) for t in result.scalars().all()]


@router.get("/tickets/{ticket_id}", response_model=SupportTicketAdminOut)
async def get_support_ticket(
    ticket_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("support:read")),
):
    ticket = await get_ticket_admin(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")
    return _ticket_out(ticket)


@router.post("/tickets/{ticket_id}/replies", response_model=SupportTicketAdminOut)
async def reply_support_ticket(
    ticket_id: UUID,
    body: SupportTicketReplyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("support:write"))],
):
    ticket = await get_ticket_admin(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")
    if ticket.status == SupportTicketStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Тикет уже закрыт")

    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите ответ")

    await add_admin_reply(db, ticket=ticket, admin=admin, message=message)
    await log_admin_action(
        db,
        admin=admin,
        action="support.ticket.reply",
        resource_type="support_ticket",
        resource_id=str(ticket_id),
    )
    await db.commit()

    refreshed = await get_ticket_admin(db, ticket_id)
    ticket = refreshed
    assert ticket is not None
    return _ticket_out(ticket)


@router.patch("/tickets/{ticket_id}/status", response_model=SupportTicketAdminOut)
async def update_support_ticket_status(
    ticket_id: UUID,
    body: SupportTicketStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("support:write"))],
):
    ticket = await get_ticket_admin(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")

    new_status = SupportTicketStatus(body.status)
    await set_ticket_status(db, ticket, new_status, admin=admin)
    await log_admin_action(
        db,
        admin=admin,
        action=f"support.ticket.status.{body.status}",
        resource_type="support_ticket",
        resource_id=str(ticket_id),
    )
    await db.commit()

    ticket = await get_ticket_admin(db, ticket_id)
    assert ticket is not None
    return _ticket_out(ticket)


@router.patch("/tickets/{ticket_id}/close", response_model=SupportTicketAdminOut)
async def close_support_ticket(
    ticket_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("support:write"))],
):
    return await update_support_ticket_status(
        ticket_id,
        SupportTicketStatusUpdate(status="closed"),
        db,
        admin,
    )
