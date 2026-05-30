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


def resolve_audio_content_type(content_type: str | None, filename: str | None) -> str | None:
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime and mime not in ("application/octet-stream", "binary/octet-stream"):
        return mime
    name = (filename or "").lower()
    if name.endswith((".m4a", ".mp4", ".caf")):
        return "audio/mp4"
    if name.endswith(".webm"):
        return "audio/webm"
    if name.endswith(".ogg"):
        return "audio/ogg"
    if name.endswith((".mp3", ".mpeg")):
        return "audio/mpeg"
    if name.endswith(".wav"):
        return "audio/wav"
    return content_type


class SpeechTranscriptionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_ogg_opus(input_bytes: bytes, input_ext: str) -> bytes:
    return _ffmpeg_convert(
        input_bytes,
        input_ext,
        [
            "-vn",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-application",
            "voip",
            "-b:a",
            "32k",
        ],
        "out.ogg",
    )


def _convert_to_lpcm_raw(input_bytes: bytes, input_ext: str) -> bytes:
    return _ffmpeg_convert(
        input_bytes,
        input_ext,
        ["-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-acodec", "pcm_s16le"],
        "out.raw",
    )


def _ffmpeg_convert(input_bytes: bytes, input_ext: str, audio_args: list[str], out_name: str) -> bytes:
    if not _ffmpeg_available():
        raise SpeechTranscriptionError(
            "ffmpeg_missing",
            "На сервере не установлен ffmpeg для конвертации аудио",
        )
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / f"in.{input_ext}"
        out = Path(tmp) / out_name
        inp.write_bytes(input_bytes)
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(inp), *audio_args, str(out)],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not out.exists() or out.stat().st_size < 128:
            err = proc.stderr.decode(errors="replace")[:300]
            logger.warning(
                "ffmpeg convert failed (%s -> %s, in=%s bytes): %s",
                input_ext,
                out_name,
                len(input_bytes),
                err,
            )
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
    source_ext = _EXT_BY_MIME.get(mime, "webm")

    attempts: list[tuple[str, bytes, str, dict[str, str], dict[str, str]]] = []

    if mime in ("audio/ogg", "audio/opus"):
        attempts.append(("oggopus", audio, "audio/ogg", {"lang": "ru-RU", "format": "oggopus"}, {}))
    elif mime in ("audio/mpeg", "audio/mp3"):
        attempts.append(("mp3", audio, "audio/mpeg", {"lang": "ru-RU", "format": "mp3"}, {}))
    elif mime in ("audio/wav", "audio/x-wav"):
        attempts.append(
            (
                "lpcm",
                audio,
                "audio/wav",
                {"lang": "ru-RU", "format": "lpcm", "sampleRateHz": "48000"},
                {},
            )
        )
    else:
        ogg = await asyncio.to_thread(_convert_to_ogg_opus, audio, source_ext)
        attempts.append(("oggopus", ogg, "audio/ogg", {"lang": "ru-RU", "format": "oggopus"}, {}))
        try:
            lpcm = await asyncio.to_thread(_convert_to_lpcm_raw, audio, source_ext)
            attempts.append(
                (
                    "lpcm",
                    lpcm,
                    "audio/wav",
                    {"lang": "ru-RU", "format": "lpcm", "sampleRateHz": "48000"},
                    {"fallback": "lpcm"},
                )
            )
        except SpeechTranscriptionError:
            pass

    headers_base = {"Authorization": f"Api-Key {settings.yandex_api_key}"}
    last_empty = False

    for fmt, payload, content_header, fmt_params, meta in attempts:
        params = {"folderId": settings.yandex_folder_id, **fmt_params}
        headers = {**headers_base, "Content-Type": content_header}
        try:
            text = await _recognize_once(payload, params, headers)
        except SpeechTranscriptionError as exc:
            if exc.code == "no_speech":
                last_empty = True
                logger.info(
                    "Yandex STT empty result (%s, %s bytes, source=%s %s bytes)",
                    fmt,
                    len(payload),
                    mime,
                    len(audio),
                )
                continue
            raise
        if text:
            if meta.get("fallback"):
                logger.info("Yandex STT succeeded via LPCM fallback (%s bytes)", len(payload))
            return text
        last_empty = True
        logger.info(
            "Yandex STT empty result (%s, %s bytes, source=%s %s bytes)",
            fmt,
            len(payload),
            mime,
            len(audio),
        )

    if last_empty:
        raise SpeechTranscriptionError("no_speech", "Речь не распознана")
    raise SpeechTranscriptionError(
        "stt_upstream_error",
        "Сервис распознавания речи временно недоступен",
    )


async def _recognize_once(payload: bytes, params: dict[str, str], headers: dict[str, str]) -> str:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(STT_URL, params=params, content=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:200]
        logger.warning("Yandex STT HTTP %s: %s", status, body)
        if status in (401, 403):
            raise SpeechTranscriptionError(
                "stt_forbidden",
                "Нет доступа к SpeechKit STT. Проверьте API-ключ и роль ai.speechkit-stt.user",
            ) from exc
        if status == 400:
            raise SpeechTranscriptionError(
                "audio_convert_failed",
                "Не удалось обработать аудиозапись",
            ) from exc
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
