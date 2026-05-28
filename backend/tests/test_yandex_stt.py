import asyncio

import pytest

from app.core.config import Settings
from app.services.yandex_stt import SpeechTranscriptionError, transcribe_audio


def test_transcribe_requires_yandex_config():
    settings = Settings(yandex_folder_id="", yandex_api_key="")
    with pytest.raises(SpeechTranscriptionError) as exc:
        asyncio.run(transcribe_audio(b"data", "audio/webm", settings))
    assert exc.value.code == "stt_not_configured"


def test_transcribe_rejects_empty_audio():
    settings = Settings(yandex_folder_id="f", yandex_api_key="k")
    with pytest.raises(SpeechTranscriptionError) as exc:
        asyncio.run(transcribe_audio(b"", "audio/webm", settings))
    assert exc.value.code == "empty_audio"
