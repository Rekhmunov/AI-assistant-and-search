"""Голосовой ввод: загрузка аудио и распознавание текста."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import SearchUserResult, get_search_user
from app.core.config import get_settings
from app.models.user import Plan
from app.services.yandex_stt import SpeechTranscriptionError, resolve_audio_content_type, transcribe_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_VOICE_BYTES = 5 * 1024 * 1024
VOICE_PRO_ONLY_MESSAGE = "Распознавание речи доступно только в Pro"


def voice_transcription_allowed(user) -> bool:
    """Guests may try voice input; logged-in Free users need Pro."""
    return bool(user.guest_key) or user.plan == Plan.PRO


class VoiceTranscribeOut(BaseModel):
    text: str


class VoiceClientReport(BaseModel):
    event: str = Field(..., max_length=64)
    bytes: int = Field(0, ge=0, le=MAX_VOICE_BYTES)
    platform: str = Field("", max_length=32)
    max_webapp: bool = False
    mime: str = Field("", max_length=64)
    elapsed_ms: int = Field(0, ge=0, le=600_000)
    api_base: str = Field("", max_length=256)
    error: str = Field("", max_length=200)


@router.post("/report")
async def voice_client_report(body: VoiceClientReport, request: Request):
    """Диагностика из MAX WebView (запрос до /transcribe или вместо него)."""
    logger.info(
        "voice client report event=%s bytes=%s platform=%s max=%s mime=%s elapsed_ms=%s api_base=%s error=%s ip=%s",
        body.event,
        body.bytes,
        body.platform,
        body.max_webapp,
        body.mime,
        body.elapsed_ms,
        body.api_base[:80],
        body.error[:120],
        request.client.host if request.client else None,
    )
    return {"ok": True}


@router.post("/transcribe", response_model=VoiceTranscribeOut)
async def transcribe_voice(
    file: Annotated[UploadFile, File(...)],
    search_user: Annotated[SearchUserResult, Depends(get_search_user)],
):
    user = search_user.user
    if not voice_transcription_allowed(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=VOICE_PRO_ONLY_MESSAGE,
        )
    raw = await file.read()
    if len(raw) > MAX_VOICE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Аудиозапись слишком длинная",
        )
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")

    settings = get_settings()
    resolved_type = resolve_audio_content_type(file.content_type, file.filename)
    logger.info(
        "voice transcribe user=%s guest=%s bytes=%s type=%s filename=%s",
        user.id,
        bool(user.guest_key),
        len(raw),
        resolved_type,
        file.filename,
    )
    try:
        text = await transcribe_audio(raw, resolved_type, settings)
    except SpeechTranscriptionError as exc:
        logger.warning(
            "voice transcribe failed: code=%s user=%s bytes=%s type=%s filename=%s",
            exc.code,
            user.id,
            len(raw),
            resolved_type,
            file.filename,
        )
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.code in ("empty_audio", "no_speech"):
            status_code = status.HTTP_400_BAD_REQUEST
        elif exc.code in ("audio_convert_failed",):
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        elif exc.code == "stt_forbidden":
            status_code = status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return VoiceTranscribeOut(text=text)
