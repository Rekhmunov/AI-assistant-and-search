"""Тесты сборки xlsx."""

from __future__ import annotations

from app.services.doc_gen_schema import DocSection, DocumentStructure
from app.services.xlsx_builder import build_xlsx_bytes


def test_build_xlsx_bytes():
    structure = DocumentStructure(
        title="Отчёт",
        sections=[DocSection(heading="Раздел 1", paragraphs=["Строка 1", "Строка 2"])],
    )
    data = build_xlsx_bytes(structure)
    assert isinstance(data, bytes)
    assert len(data) > 100
    assert data[:2] == b"PK"
