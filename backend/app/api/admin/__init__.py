from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import admins, audit, auth, blog, broadcasts, dashboard, legal, payments, settings, support, system, users
from app.api.admin.dashboard import dashboard as dashboard_metrics
from app.api.deps import get_db
from app.core.admin_permissions import require_permission

router = APIRouter(prefix="/admin")

router.include_router(auth.router)
router.include_router(dashboard.router)
router.include_router(broadcasts.router)
router.include_router(users.router)
router.include_router(system.router)
router.include_router(payments.router)
router.include_router(settings.router)
router.include_router(legal.router)
router.include_router(blog.router)
router.include_router(support.router)
router.include_router(audit.router)
router.include_router(admins.router)


@router.get("/metrics")
async def legacy_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin=Depends(require_permission("dashboard:read")),
):
    """Backward-compatible metrics for older admin builds."""
    data = await dashboard_metrics(db, _admin)
    return {
        "users_total": data.users_total,
        "users_pro": data.users_pro,
        "broadcasts_total": data.broadcasts_total,
    }
