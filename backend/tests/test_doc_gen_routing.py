from app.services.doc_gen_routing import resolve_output_format, wants_document_generation


def test_wants_document_generation_positive():
    assert wants_document_generation("Создай документ публичную оферту")
    assert wants_document_generation("Сгенерируй docx из текста выше")
    assert wants_document_generation("Оформи оферту в word")
    assert wants_document_generation("Преобразуй текст выше в документ")
    assert wants_document_generation("Экспортируй ответ в docx")
    assert wants_document_generation("документ: заявление на отпуск с 1 по 15 июня")


def test_wants_document_generation_chat_not_file():
    assert not wants_document_generation("Сформируй публичную оферту для Glosix")
    assert not wants_document_generation("Сгенерируй публичную оферту")
    assert not wants_document_generation("Напиши в чат публичную оферту")
    assert not wants_document_generation("Подготовь договор аренды")
    assert not wants_document_generation("Сделай заявление на отпуск")
    assert not wants_document_generation("Напиши служебную записку")


def test_wants_document_generation_negative():
    assert not wants_document_generation("Курс доллара")
    assert not wants_document_generation("Что на фото?")
    assert not wants_document_generation("Что такое публичная оферта")
    assert not wants_document_generation("Объясни разницу между договором и соглашением")


def test_resolve_output_format():
    assert resolve_output_format("договор") == "docx"
    assert resolve_output_format("сохрани в pdf") == "pdf"
