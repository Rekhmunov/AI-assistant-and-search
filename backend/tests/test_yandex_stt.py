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


def test_stt_http_status_maps_to_forbidden(monkeypatch):
    import httpx

    class FakeResponse:
        status_code = 403
        text = "Permission denied"

        def json(self):
            return {}

    class FakeHTTPStatusError(httpx.HTTPStatusError):
        def __init__(self):
            request = httpx.Request("POST", "https://example.com")
            response = httpx.Response(403, request=request, text="Permission denied")
            super().__init__("403", request=request, response=response)

    async def fake_post(*_args, **_kwargs):
        raise FakeHTTPStatusError()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        post = fake_post

    settings = Settings(yandex_folder_id="f", yandex_api_key="k")
    monkeypatch.setattr("app.services.yandex_stt.httpx.AsyncClient", lambda **_kw: FakeClient())
    monkeypatch.setattr(
        "app.services.yandex_stt._convert_to_ogg_opus",
        lambda audio, ext: audio,
    )

    with pytest.raises(SpeechTranscriptionError) as exc:
        asyncio.run(transcribe_audio(b"audio-bytes", "audio/webm", settings))
    assert exc.value.code == "stt_forbidden"


def test_transcribe_falls_back_to_lpcm_after_empty_ogg(monkeypatch):
    calls: list[str] = []

    async def fake_recognize(_payload, params, _headers):
        calls.append(params["format"])
        if params["format"] == "oggopus":
            raise SpeechTranscriptionError("no_speech", "Речь не распознана")
        return "привет"

    settings = Settings(yandex_folder_id="f", yandex_api_key="k")
    monkeypatch.setattr("app.services.yandex_stt._convert_to_ogg_opus", lambda audio, ext: b"ogg")
    monkeypatch.setattr("app.services.yandex_stt._convert_to_lpcm_raw", lambda audio, ext: b"lpcm")
    monkeypatch.setattr("app.services.yandex_stt._recognize_once", fake_recognize)

    text = asyncio.run(transcribe_audio(b"audio-bytes", "audio/mp4", settings))
    assert text == "привет"
    assert calls == ["oggopus", "lpcm"]
