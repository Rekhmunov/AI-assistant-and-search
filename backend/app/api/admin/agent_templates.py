"""Управление шаблонами агентов из админки."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.admin_permissions import require_permission
from app.models.admin_user import AdminUser
from app.services.agent.template_visibility import (
    ALL_TEMPLATES,
    get_template_visibility,
    set_template_visibility,
)
from app.services.agent.templates import TEMPLATE_TITLES

router = APIRouter(prefix="/agent-templates", tags=["admin-agent-templates"])


class TemplateVisibilityUpdate(BaseModel):
    mode: str  # "all" | "users"
    user_ids: list[str] = []  # UUID-строки пользователей


class TemplateInfo(BaseModel):
    id: str
    title: str
    mode: str
    user_ids: list[str]  # UUID-строки пользователей


@router.get("", response_model=list[TemplateInfo])
async def list_agent_templates(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client=Depends(get_redis),
    admin: AdminUser = Depends(require_permission("settings:read")),
):
    """Список шаблонов агентов с настройками видимости."""
    visibility = await get_template_visibility(db, redis_client)
    # "assistant" создаётся автоматически — управлять его видимостью не нужно
    _HIDDEN = {"assistant"}
    result = []
    for tid in ALL_TEMPLATES:
        if tid in _HIDDEN:
            continue
        cfg = visibility.get(tid, {"mode": "all", "user_ids": []})
        result.append(
            TemplateInfo(
                id=tid,
                title=TEMPLATE_TITLES.get(tid, tid),
                mode=cfg.get("mode", "all"),
                user_ids=cfg.get("user_ids", []),
            )
        )
    return result


@router.patch("/{template_id}", response_model=list[TemplateInfo])
async def update_template_visibility(
    template_id: str,
    body: TemplateVisibilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client=Depends(get_redis),
    admin: AdminUser = Depends(require_permission("settings:write")),
):
    """Обновить видимость одного шаблона агента."""
    if template_id not in ALL_TEMPLATES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    if body.mode not in ("all", "users"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode: 'all' или 'users'")

    updated = await set_template_visibility(
        db, redis_client, template_id, body.mode, [str(uid) for uid in body.user_ids], admin.id
    )
    await db.commit()

    result = []
    for tid in ALL_TEMPLATES:
        cfg = updated.get(tid, {"mode": "all", "user_ids": []})
        result.append(
            TemplateInfo(
                id=tid,
                title=TEMPLATE_TITLES.get(tid, tid),
                mode=cfg.get("mode", "all"),
                user_ids=cfg.get("user_ids", []),
            )
        )
    return result
