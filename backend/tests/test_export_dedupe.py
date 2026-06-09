from app.services.export_dedupe import export_content_hash


def test_export_content_hash_differs_by_format():
    content = "# Заголовок\n\nТекст документа достаточной длины для экспорта."
    docx = export_content_hash(fmt="docx", content=content, title_hint="A")
    pdf = export_content_hash(fmt="pdf", content=content, title_hint="A")
    md = export_content_hash(fmt="md", content=content, title_hint="A")
    assert docx != pdf != md


def test_export_content_hash_stable_for_same_input():
    content = "# Заголовок\n\nТекст документа достаточной длины для экспорта."
    a = export_content_hash(fmt="docx", content=content, title_hint="Отчёт")
    b = export_content_hash(fmt="docx", content=content, title_hint="Отчёт")
    assert a == b
