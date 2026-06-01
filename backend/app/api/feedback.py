"""Оценки ответов ассистента."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import GUEST_HEADER, SearchUserResult, get_db, get_search_user, set_guest_cookie
from app.models.message import Message, MessageRole
from app.models.message_feedback import FeedbackRating, MessageFeedback
from app.models.thread import Thread
from app.models.user import User
from app.schemas.feedback import (
    MessageFeedbackCreate,
    MessageFeedbackOut,
    MessageFeedbackSubmitOut,
    reason_label,
    validate_down_feedback,
)

router = APIRouter(prefix="/messages", tags=["feedback"])


async def _message_for_user(
    db: AsyncSession, message_id: UUID, user: User
) -> Message | None:
    result = await db.execute(
        select(Message)
        .join(Thread, Thread.id == Message.thread_id)
        .where(
            Message.id == message_id,
            Message.role == MessageRole.ASSISTANT,
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


@router.post("/{message_id}/feedback", response_model=MessageFeedbackSubmitOut)
async def submit_message_feedback(
    message_id: UUID,
    body: MessageFeedbackCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[SearchUserResult, Depends(get_search_user)],
):
    user = actor.user
    if actor.new_guest_key:
        set_guest_cookie(response, actor.new_guest_key)
        response.headers[GUEST_HEADER] = actor.new_guest_key

    msg = await _message_for_user(db, message_id, user)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сообщение не найдено")

    if body.rating == "up":
        reason_code = None
        comment = None
    else:
        try:
            validate_down_feedback(body.reason_code, body.comment)
        except ValueError as e:
            code = str(e)
            if code == "reason_required":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Укажите причину оценки",
                ) from e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Введите комментарий для варианта «Другое»",
            ) from e
        reason_code = body.reason_code
        comment = body.comment

    existing = await db.scalar(
        select(MessageFeedback).where(
            MessageFeedback.message_id == message_id,
            MessageFeedback.user_id == user.id,
        )
    )
    rating_enum = FeedbackRating.UP if body.rating == "up" else FeedbackRating.DOWN
    if existing:
        existing.rating = rating_enum
        existing.reason_code = reason_code
        existing.comment = comment
        row = existing
    else:
        row = MessageFeedback(
            message_id=message_id,
            user_id=user.id,
            rating=rating_enum,
            reason_code=reason_code,
            comment=comment,
        )
        db.add(row)
    await db.commit()
    await db.refresh(row)

    out = MessageFeedbackOut(
        rating=body.rating,
        reason_code=row.reason_code,
        reason_label=reason_label(row.reason_code),
        comment=row.comment,
    )
    return MessageFeedbackSubmitOut(feedback=out)
