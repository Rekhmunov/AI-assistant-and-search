from app.services.doc_gen_schema import DocumentStructure, DocSection
from app.services.docx_builder import build_docx_bytes


def test_build_docx_bytes():
    data = build_docx_bytes(
        DocumentStructure(title="Тест", sections=[DocSection(heading="Раздел", paragraphs=["Абзац"])]),
        show_glosix_footer=True,
    )
    assert data[:2] == b"PK"
    assert len(data) > 200
