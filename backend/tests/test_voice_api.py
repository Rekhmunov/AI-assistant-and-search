import uuid

from app.api.voice import voice_transcription_allowed
from app.models.user import Plan, User
from app.services.yandex_stt import resolve_audio_content_type


def test_voice_transcription_allowed_for_guest():
    user = User(id=uuid.uuid4(), guest_key="guest-key", plan=Plan.FREE)
    assert voice_transcription_allowed(user) is True


def test_voice_transcription_allowed_for_pro():
    user = User(id=uuid.uuid4(), email="a@b.c", plan=Plan.PRO)
    assert voice_transcription_allowed(user) is True


def test_voice_transcription_blocked_for_free_logged_in():
    user = User(id=uuid.uuid4(), email="a@b.c", plan=Plan.FREE)
    assert voice_transcription_allowed(user) is False


def test_resolve_audio_content_type_from_filename():
    assert resolve_audio_content_type("application/octet-stream", "voice.m4a") == "audio/mp4"
    assert resolve_audio_content_type(None, "voice.webm") == "audio/webm"
    assert resolve_audio_content_type("audio/webm;codecs=opus", "voice.webm") == "audio/webm"
