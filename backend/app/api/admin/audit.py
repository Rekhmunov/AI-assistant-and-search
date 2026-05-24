from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_audit import AdminAuditLog
from app.schemas.admin import AuditLogOut

router = APIRouter(prefix="/audit", tags=["admin-audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=100, le=200),
    _admin=Depends(require_permission("audit:read")),
):
    result = await db.execute(
        select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit)
    )
    return result.scalars().all()
