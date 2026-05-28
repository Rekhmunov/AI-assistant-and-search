"""Распознавание речи через Yandex SpeechKit STT (для миниаппа MAX и браузеров без Web Speech API)."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)

STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

_EXT_BY_MIME: dict[str, str] = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "video/mp4": "mp4",
}


class SpeechTranscriptionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_ogg_opus(input_bytes: bytes, input_ext: str) -> bytes:
    if not _ffmpeg_available():
        raise SpeechTranscriptionError(
            "ffmpeg_missing",
            "На сервере не установлен ffmpeg для конвертации аудио",
        )
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / f"in.{input_ext}"
        out = Path(tmp) / "out.ogg"
        inp.write_bytes(input_bytes)
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(inp),
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-vn",
                str(out),
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")[:300]
            logger.warning("ffmpeg convert failed: %s", err)
            raise SpeechTranscriptionError(
                "audio_convert_failed",
                "Не удалось обработать аудиозапись",
            )
        return out.read_bytes()


async def transcribe_audio(
    audio: bytes,
    content_type: str | None,
    settings: Settings,
) -> str:
    if not settings.yandex_configured:
        raise SpeechTranscriptionError(
            "stt_not_configured",
            "Распознавание речи не настроено на сервере",
        )
    if not audio:
        raise SpeechTranscriptionError("empty_audio", "Пустая аудиозапись")

    mime = (content_type or "audio/webm").split(";")[0].strip().lower()
    fmt = "oggopus"
    payload = audio

    if mime in ("audio/ogg", "audio/opus"):
        payload = audio
    elif mime in ("audio/mpeg", "audio/mp3"):
        fmt = "mp3"
        payload = audio
    elif mime in ("audio/wav", "audio/x-wav"):
        fmt = "lpcm"
        payload = audio
    else:
        ext = _EXT_BY_MIME.get(mime, "webm")
        payload = await asyncio.to_thread(_convert_to_ogg_opus, audio, ext)

    params: dict[str, str] = {
        "folderId": settings.yandex_folder_id,
        "lang": "ru-RU",
        "format": fmt,
    }
    if fmt == "lpcm":
        params["sampleRateHz"] = "48000"

    headers = {
        "Authorization": f"Api-Key {settings.yandex_api_key}",
    }
    if fmt == "oggopus":
        headers["Content-Type"] = "audio/ogg"
    elif fmt == "mp3":
        headers["Content-Type"] = "audio/mpeg"
    else:
        headers["Content-Type"] = "audio/wav"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(STT_URL, params=params, content=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:200]
        logger.warning("Yandex STT HTTP %s: %s", exc.response.status_code, body)
        raise SpeechTranscriptionError(
            "stt_upstream_error",
            "Сервис распознавания речи временно недоступен",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Yandex STT request failed: %s", exc)
        raise SpeechTranscriptionError(
            "stt_upstream_error",
            "Сервис распознавания речи временно недоступен",
        ) from exc

    text = (data.get("result") or "").strip()
    if not text:
        raise SpeechTranscriptionError("no_speech", "Речь не распознана")
    return text
