import pytest

from app.services.doc_gen_schema import DocumentStructureError, parse_document_structure


def test_parse_document_structure_minimal():
    raw = """{"title": "Заявление", "sections": [{"heading": "1", "paragraphs": ["Текст"]}], "tables": []}"""
    doc = parse_document_structure(raw)
    assert doc.title == "Заявление"
    assert len(doc.sections) == 1


def test_parse_document_structure_rejects_empty():
    with pytest.raises(DocumentStructureError):
        parse_document_structure('{"title": "X", "sections": [], "tables": []}')
