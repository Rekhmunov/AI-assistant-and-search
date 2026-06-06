from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.schemas.support import SupportTicketAdminOut
from app.services.admin_audit import log_admin_action

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
    )


@router.get("/tickets", response_model=list[SupportTicketAdminOut])
async def list_support_tickets(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("support:read")),
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
):
    query = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(limit)
    if status_filter in ("open", "closed"):
        query = query.where(SupportTicket.status == SupportTicketStatus(status_filter))
    result = await db.execute(query)
    return [_ticket_out(t) for t in result.scalars().all()]


@router.patch("/tickets/{ticket_id}/close", response_model=SupportTicketAdminOut)
async def close_support_ticket(
    ticket_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("support:write"))],
):
    result = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тикет не найден")
    if ticket.status == SupportTicketStatus.CLOSED:
        return _ticket_out(ticket)

    ticket.status = SupportTicketStatus.CLOSED
    ticket.closed_at = datetime.now(timezone.utc)
    ticket.closed_by_admin_id = admin.id

    await log_admin_action(
        db,
        admin=admin,
        action="support.ticket.close",
        resource_type="support_ticket",
        resource_id=str(ticket_id),
    )
    await db.commit()
    await db.refresh(ticket)
    return _ticket_out(ticket)
