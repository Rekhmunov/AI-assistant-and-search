from app.schemas.admin import BroadcastCreate
from app.services.bot_media import max_bot_media_attachments, media_type_from_filename


def test_media_type_from_filename():
    assert media_type_from_filename("photo.jpg") == "image"
    assert media_type_from_filename("clip.MP4") == "video"
    assert media_type_from_filename("doc.pdf") is None


def test_max_bot_media_attachments():
    assert max_bot_media_attachments("none", "tok") is None
    assert max_bot_media_attachments("image", "") is None
    assert max_bot_media_attachments("image", "abc123") == [
        {"type": "image", "payload": {"token": "abc123"}},
    ]
    assert max_bot_media_attachments("video", "vidtok") == [
        {"type": "video", "payload": {"token": "vidtok"}},
    ]


def test_broadcast_create_requires_text_or_media():
    BroadcastCreate(text="Привет", audience="all")
    BroadcastCreate(
        text="",
        audience="all",
        media_type="image",
        media_token="tok",
        media_filename="a.png",
    )


def test_broadcast_create_rejects_media_without_token():
    try:
        BroadcastCreate(text="", audience="all", media_type="image")
        assert False, "expected validation error"
    except ValueError:
        pass
