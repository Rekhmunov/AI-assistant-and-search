from app.services.image_bytes import detect_image_mime, is_valid_image_bytes

_JPEG_MIN = b"\xff\xd8\xff\xe0" + b"\x00" * 125
_PNG_MIN = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120


def test_detect_jpeg():
    assert detect_image_mime(_JPEG_MIN) == "image/jpeg"


def test_detect_png():
    assert detect_image_mime(_PNG_MIN) == "image/png"


def test_reject_garbage():
    assert detect_image_mime(b"not-an-image") is None
    assert not is_valid_image_bytes(b"html error page" * 20)
