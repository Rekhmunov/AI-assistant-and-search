from app.services.doc_gen_plain import structure_from_plain_text


def test_structure_from_offer_like_text():
    text = """ПУБЛИЧНАЯ ОФЕРТА
на использование онлайн-сервиса

Термины и определения
1.1. Исполнитель — ООО Тест, ИНН 123.
1.2. Сервис — веб-платформа с ИИ.

Предмет договора
2.1. Исполнитель предоставляет доступ к Сервису.
ooke
"""
    doc = structure_from_plain_text(text)
    assert doc is not None
    assert "оферт" in doc.title.lower()
    assert any("Термины" in (s.heading or "") for s in doc.sections)
    assert any("1.1." in p for s in doc.sections for p in s.paragraphs)
    assert not any("ooke" in p for s in doc.sections for p in s.paragraphs)
