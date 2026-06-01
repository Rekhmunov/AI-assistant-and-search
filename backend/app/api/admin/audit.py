from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.models.admin_audit import AdminAuditLog
from app.schemas.admin import AuditLogOut, AuditLogPage

router = APIRouter(prefix="/audit", tags=["admin-audit"])


@router.get("", response_model=AuditLogPage)
async def list_audit(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    _admin=Depends(require_permission("audit:read")),
):
    total = int(await db.scalar(select(func.count()).select_from(AdminAuditLog)) or 0)
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AdminAuditLog)
        .order_by(AdminAuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = [AuditLogOut.model_validate(row) for row in result.scalars().all()]
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)
