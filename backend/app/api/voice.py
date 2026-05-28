"""Голосовой ввод: загрузка аудио и распознавание текста."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.services.yandex_stt import SpeechTranscriptionError, transcribe_audio

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_VOICE_BYTES = 5 * 1024 * 1024


class VoiceTranscribeOut(BaseModel):
    text: str


@router.post("/transcribe", response_model=VoiceTranscribeOut)
async def transcribe_voice(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_user)],
):
    _ = user
    raw = await file.read()
    if len(raw) > MAX_VOICE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Аудиозапись слишком длинная",
        )
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пустой файл")

    settings = get_settings()
    try:
        text = await transcribe_audio(raw, file.content_type, settings)
    except SpeechTranscriptionError as exc:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        if exc.code in ("empty_audio", "no_speech"):
            status_code = status.HTTP_400_BAD_REQUEST
        elif exc.code == "audio_convert_failed":
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return VoiceTranscribeOut(text=text)
