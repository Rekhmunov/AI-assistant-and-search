"""Тесты отправки файлов агентом в MAX."""

from __future__ import annotations

from app.services.agent.document_delivery import (
    infer_output_format,
    wants_document_delivery,
    wants_image_delivery,
)
from app.services.agent.file_delivery import attachment_type_for_filename, max_file_attachment
from app.services.bot_media import max_bot_media_attachments


def test_infer_output_format():
    assert infer_output_format("пришли отчёт в excel") == "xlsx"
    assert infer_output_format("отправь pdf с договором") == "pdf"
    assert infer_output_format("сделай word документ") == "docx"
    assert infer_output_format("текст", "pdf") == "pdf"


def test_wants_document_delivery():
    assert wants_document_delivery("каждый день отправляй отчёт в pdf")
    assert wants_document_delivery("создай документ: договор оферты")
    assert not wants_document_delivery("напоминай про встречу")


def test_wants_image_delivery():
    assert wants_image_delivery("пришли картинку заката")
    assert not wants_image_delivery("пришли pdf отчёт")


def test_attachment_type_for_filename():
    assert attachment_type_for_filename("photo.png") == "image"
    assert attachment_type_for_filename("report.xlsx") == "file"


def test_max_file_attachment_shape():
    assert max_file_attachment("tok123") == {
        "type": "file",
        "payload": {"token": "tok123"},
    }
    assert max_bot_media_attachments("file", "tok123") == [
        {"type": "file", "payload": {"token": "tok123"}},
    ]
