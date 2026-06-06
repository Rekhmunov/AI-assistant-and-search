from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.request_security import verify_allowed_origin
from app.models.support_ticket import SupportTicket, SupportTicketStatus
from app.models.user import User
from app.schemas.support import SupportTicketCreate, SupportTicketCreateOut

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=SupportTicketCreateOut, status_code=status.HTTP_201_CREATED)
async def create_support_ticket(
    request: Request,
    body: SupportTicketCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    verify_allowed_origin(request)
    message = body.message.strip()
    if len(message) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Введите сообщение")

    ticket = SupportTicket(
        user_id=user.id,
        user_email=user.email,
        user_max_user_id=user.max_user_id,
        source=(body.source or "general").strip()[:64] or "general",
        message=message,
        status=SupportTicketStatus.OPEN,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return SupportTicketCreateOut(id=ticket.id, created_at=ticket.created_at)
