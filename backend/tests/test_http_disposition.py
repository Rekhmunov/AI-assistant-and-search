from starlette.responses import Response

from app.services.http_disposition import attachment_content_disposition


def test_attachment_disposition_encodes_cyrillic():
    name = "Заявление-на-отпуск-91fc941e.docx"
    header = attachment_content_disposition(name)
    assert "filename*=" in header
    Response(content=b"PK", headers={"Content-Disposition": header})


def test_attachment_disposition_ascii():
    header = attachment_content_disposition("report.docx")
    assert 'filename="report.docx"' in header
    Response(content=b"PK", headers={"Content-Disposition": header})
