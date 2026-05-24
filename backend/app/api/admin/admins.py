from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_permissions import require_permission
from app.core.security import hash_password
from app.models.admin_user import AdminUser
from app.schemas.admin import AdminUserCreate, AdminUserOut, AdminUserUpdate
from app.services.admin_audit import log_admin_action

router = APIRouter(prefix="/admins", tags=["admin-users-mgmt"])


@router.get("", response_model=list[AdminUserOut])
async def list_admins(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("admins:read")),
):
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at.asc()))
    return result.scalars().all()


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: AdminUserCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[AdminUser, Depends(require_permission("admins:write"))],
):
    existing = await db.execute(select(AdminUser).where(AdminUser.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    row = AdminUser(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(row)
    await log_admin_action(
        db,
        admin=admin,
        action="admin.create",
        resource_type="admin_user",
        resource_id=str(row.id),
        details={"email": row.email, "role": row.role.value},
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return row


@router.patch("/{admin_id}", response_model=AdminUserOut)
async def update_admin(
    admin_id: UUID,
    body: AdminUserUpdate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[AdminUser, Depends(require_permission("admins:write"))],
):
    result = await db.execute(select(AdminUser).where(AdminUser.id == admin_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    changes: dict = {}
    if body.role is not None:
        row.role = body.role
        changes["role"] = body.role.value
    if body.is_active is not None:
        row.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.password:
        row.password_hash = hash_password(body.password)
        changes["password"] = "changed"

    await log_admin_action(
        db,
        admin=current,
        action="admin.update",
        resource_type="admin_user",
        resource_id=str(admin_id),
        details=changes,
        ip_address=request.client.host if request.client else None,
    )
    return row
