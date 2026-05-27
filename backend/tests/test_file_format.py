from app.services.file_format import resolve_upload_extension, sniff_ext_from_bytes


def test_sniff_jpeg():
    assert sniff_ext_from_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "jpg"


def test_sniff_png():
    assert sniff_ext_from_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == "png"


def test_resolve_extension_from_mime_without_ext():
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert resolve_upload_extension("blob", "image/jpeg", data) == "jpg"


def test_resolve_extension_heic_sniff():
    data = b"\x00" * 4 + b"ftyp" + b"heic" + b"\x00" * 40
    assert resolve_upload_extension("photo", None, data) == "heic"
