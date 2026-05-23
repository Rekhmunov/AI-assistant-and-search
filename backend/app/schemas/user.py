from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.user import Plan


class UserProfile(BaseModel):
    id: UUID
    first_name: str | None
    last_name: str | None
    username: str | None
    language: str
    plan: Plan
    plan_expires_at: datetime | None
    searches_today: int
    searches_limit: int

    model_config = {"from_attributes": True}
