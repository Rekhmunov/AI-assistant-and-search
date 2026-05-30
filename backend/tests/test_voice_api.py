from app.services.yandex_stt import resolve_audio_content_type


def test_resolve_audio_content_type_from_filename():
    assert resolve_audio_content_type("application/octet-stream", "voice.m4a") == "audio/mp4"
    assert resolve_audio_content_type(None, "voice.webm") == "audio/webm"
    assert resolve_audio_content_type("audio/webm;codecs=opus", "voice.webm") == "audio/webm"
