"""Проверка magic bytes для URL картинок."""

from app.services.image_url_validation import _magic_is_image


def test_magic_bytes():
    assert _magic_is_image(b"\xff\xd8\xff\xe0" + b"x" * 400)
    assert _magic_is_image(b"\x89PNG\r\n\x1a\n" + b"x" * 400)
    assert _magic_is_image(b"GIF89a" + b"x" * 400)
    assert _magic_is_image(b"RIFFxxxxWEBP" + b"x" * 400)
    assert not _magic_is_image(b"<html>" + b"x" * 400)
    assert not _magic_is_image(b"\xff\xd8\xff")
