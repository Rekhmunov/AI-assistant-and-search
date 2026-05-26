from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.admin_user import AdminRole
from app.models.broadcast import BroadcastAudience, BroadcastStatus


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class AdminUserOut(BaseModel):
    id: UUID
    email: str
    role: AdminRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: AdminRole = AdminRole.SUPPORT


class AdminUserUpdate(BaseModel):
    role: AdminRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class DashboardMetrics(BaseModel):
    users_total: int
    users_new_7d: int
    users_pro: int
    users_active_24h: int
    broadcasts_total: int
    messages_today: int
    searches_today_estimate: int
    yandex_configured: bool
    redis_ok: bool
    maintenance_mode: bool


class BroadcastCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    audience: BroadcastAudience = BroadcastAudience.ALL


class BroadcastOut(BaseModel):
    id: UUID
    text: str
    audience: BroadcastAudience
    status: BroadcastStatus
    sent_count: int
    failed_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BroadcastLogOut(BaseModel):
    id: UUID
    user_id: UUID
    status: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AudiencePreview(BaseModel):
    audience: BroadcastAudience
    recipient_count: int


class UserAdminOut(BaseModel):
    id: UUID
    max_user_id: int | None = None
    email: str | None = None
    first_name: str | None
    last_name: str | None
    username: str | None
    plan: str
    plan_expires_at: datetime | None
    created_at: datetime
    deleted_at: datetime | None
    searches_today: int = 0
    searches_limit: int = 0
    threads_count: int = 0
    is_guest: bool = False

    model_config = {"from_attributes": True}


class UserAdminUpdate(BaseModel):
    plan: str | None = None
    plan_expires_at: datetime | None = None
    banned: bool | None = None


class GrantProRequest(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class SubscriptionOut(BaseModel):
    id: UUID
    user_id: UUID
    yookassa_payment_id: str | None
    status: str
    amount_rub: int
    created_at: datetime
    activated_at: datetime | None
    user_email_hint: str | None = None

    model_config = {"from_attributes": True}


class ProviderOptionOut(BaseModel):
    id: str
    label: str
    configured: bool
    hint: str | None = None


class PromptFieldOut(BaseModel):
    id: str
    label: str
    group: str
    provider: str
    setting_key: str
    description: str = ""
    rows: int = 8
    value: str
    default: str


class SettingsBundleOut(BaseModel):
    settings: dict[str, Any]
    llm_providers: list[ProviderOptionOut]
    search_providers: list[ProviderOptionOut]
    prompts: list[PromptFieldOut]


class SettingsOut(BaseModel):
    settings: dict[str, Any]


class SettingsUpdate(BaseModel):
    settings: dict[str, Any]


class AdminThreadListItem(BaseModel):
    id: UUID
    title: str
    message_count: int
    last_message_at: datetime
    created_at: datetime
    deleted_at: datetime | None = None
    deleted_by_user: bool = False


class AdminMessageDebugOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    sources: list[dict[str, Any]] | None = None
    follow_up_questions: list[str] | None = None
    debug_trace: dict[str, Any] | None = None


class AdminSearchTurnOut(BaseModel):
    """Один поисковый цикл: вопрос пользователя + ответ ассистента с отладкой."""

    user_message: AdminMessageDebugOut
    assistant_message: AdminMessageDebugOut | None = None


class AdminThreadDebugOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    last_message_at: datetime
    deleted_at: datetime | None
    deleted_by_user: bool
    turns: list[AdminSearchTurnOut]


class AuditLogOut(BaseModel):
    id: UUID
    admin_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
