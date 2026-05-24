from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.admin_user import AdminRole, AdminUser


async def ensure_bootstrap_admin(db: AsyncSession) -> None:
    settings = get_settings()
    if not settings.admin_bootstrap_email or not settings.admin_bootstrap_password:
        return

    count = await db.scalar(select(func.count()).select_from(AdminUser))
    if count and count > 0:
        return

    admin = AdminUser(
        email=settings.admin_bootstrap_email.strip().lower(),
        password_hash=hash_password(settings.admin_bootstrap_password),
        role=AdminRole.OWNER,
        is_active=True,
    )
    db.add(admin)
    await db.flush()
