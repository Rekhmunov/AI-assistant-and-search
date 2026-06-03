from app.services.doc_gen_routing import resolve_output_format, wants_document_generation


def test_wants_document_generation_positive():
    assert wants_document_generation("Составь договор купли-продажи квартиры")
    assert wants_document_generation("Сделай заявление на отпуск")
    assert wants_document_generation("Оформи документ word с планом проекта")
    assert wants_document_generation("Сгенерируй публичную оферту для Glosix")


def test_wants_document_generation_negative():
    assert not wants_document_generation("Курс доллара")
    assert not wants_document_generation("Что на фото?")


def test_resolve_output_format():
    assert resolve_output_format("договор") == "docx"
    assert resolve_output_format("сохрани в pdf") == "pdf"
