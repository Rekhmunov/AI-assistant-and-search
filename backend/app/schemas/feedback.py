from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.message_feedback import FEEDBACK_REASON_LABELS, FeedbackReasonCode

ReasonCode = Literal["outdated", "inaccurate", "wrong_sources", "other"]


class MessageFeedbackCreate(BaseModel):
    rating: Literal["up", "down"]
    reason_code: ReasonCode | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def strip_comment(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class MessageFeedbackOut(BaseModel):
    rating: Literal["up", "down"]
    reason_code: str | None = None
    reason_label: str | None = None
    comment: str | None = None


class MessageFeedbackSubmitOut(BaseModel):
    ok: bool = True
    feedback: MessageFeedbackOut


def reason_label(code: str | None) -> str | None:
    if not code:
        return None
    return FEEDBACK_REASON_LABELS.get(code)


def validate_down_feedback(reason_code: str | None, comment: str | None) -> None:
    if not reason_code or reason_code not in {c.value for c in FeedbackReasonCode}:
        raise ValueError("reason_required")
    if reason_code == FeedbackReasonCode.OTHER.value and not comment:
        raise ValueError("comment_required")
