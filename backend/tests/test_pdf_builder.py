from app.services.doc_gen_schema import DocSection, DocumentStructure
from app.services.pdf_builder import build_pdf_bytes


def test_build_pdf_bytes():
    structure = DocumentStructure(
        title="Тестовый документ",
        sections=[
            DocSection(heading="Раздел 1", paragraphs=["Первый абзац.", "Второй абзац."]),
        ],
        tables=[],
    )
    data = build_pdf_bytes(structure, show_glosix_footer=True)
    assert data.startswith(b"%PDF")
    assert len(data) > 500
