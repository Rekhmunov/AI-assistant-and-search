import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit import AdminAuditLog
from app.models.admin_user import AdminUser


async def log_admin_action(
    db: AsyncSession,
    *,
    admin: AdminUser | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        admin_user_id=admin.id if admin else None,
        admin_email=admin.email if admin else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
    return entry
