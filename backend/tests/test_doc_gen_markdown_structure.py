from app.services.doc_gen_markdown_structure import resolve_export_structure, structure_from_markdown


def test_structure_from_markdown_headings():
    text = "# Публичная оферта\n\n## 1. Термины\n\nОпределения сторон.\n\n## 2. Предмет\n\nПредмет договора."
    structure = structure_from_markdown(text)
    assert structure is not None
    assert structure.title == "Публичная оферта"
    assert len(structure.sections) >= 2
    assert structure.sections[0].heading == "1. Термины"


def test_resolve_export_structure_from_markdown():
    md = "# Договор\n\n## Раздел\n\nАбзац текста документа для экспорта в файл."
    structure = resolve_export_structure(md)
    assert structure is not None
    assert structure.title == "Договор"
