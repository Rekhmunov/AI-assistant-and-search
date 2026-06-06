from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_admin
from app.models.admin_user import AdminRole, AdminUser

ROLE_PERMISSIONS: dict[str, set[str]] = {
    AdminRole.OWNER.value: {
        "dashboard:read",
        "broadcasts:read",
        "broadcasts:write",
        "users:read",
        "users:write",
        "payments:read",
        "payments:write",
        "settings:read",
        "settings:write",
        "legal:read",
        "legal:write",
        "support:read",
        "support:write",
        "audit:read",
        "admins:read",
        "admins:write",
    },
    AdminRole.SUPPORT.value: {
        "dashboard:read",
        "users:read",
        "users:write",
        "payments:read",
        "payments:write",
        "support:read",
        "support:write",
        "audit:read",
    },
    AdminRole.MARKETING.value: {
        "dashboard:read",
        "broadcasts:read",
        "broadcasts:write",
        "audit:read",
    },
}


def admin_has_permission(admin: AdminUser, permission: str) -> bool:
    if not admin.is_active:
        return False
    perms = ROLE_PERMISSIONS.get(admin.role.value, set())
    return permission in perms


def require_permission(permission: str) -> Callable:
    async def _checker(admin: Annotated[AdminUser, Depends(get_current_admin)]) -> AdminUser:
        if not admin_has_permission(admin, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return admin

    return _checker
