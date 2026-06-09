from app.models.message import Message, MessageRole
from app.services.doc_gen_context import (
    build_doc_gen_user_message,
    prior_assistant_source_text,
    should_attach_prior_material,
    wants_prior_thread_material,
)


def _assistant(text: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, content=text, thread_id=None)  # type: ignore[arg-type]


def test_wants_prior_from_phrase():
    assert wants_prior_thread_material("Сгенерируй документ оферту из текста выше")


def test_should_attach_with_long_prior_answer():
    prior = [
        _assistant("Короткий ответ"),
        _assistant("ПУБЛИЧНАЯ ОФЕРТА\n" + "1. Термины\n" * 80),
    ]
    assert should_attach_prior_material("Сгенерируй документ оферту из текста выше", prior)


def test_build_message_includes_source():
    offer = "ПУБЛИЧНАЯ ОФЕРТА\n2. Предмет договора\nКомпания обязуется…"
    prior = [_assistant(offer)]
    out = build_doc_gen_user_message("Сделай документ из текста выше", prior)
    assert "Исходный материал из диалога" in out
    assert "ПУБЛИЧНАЯ ОФЕРТА" in out
    assert "2. Предмет договора" in out


def test_build_message_query_only_without_prior():
    out = build_doc_gen_user_message("Сделай заявление на отпуск", [])
    assert out == "Сделай заявление на отпуск"


def test_prior_source_from_markdown_attachment():
    short_intro = "Ниже оформлен текст из предыдущего ответа."
    long_md = "# Оферта\n\n" + "Раздел текста.\n" * 40
    prior = [
        _assistant(short_intro),
    ]
    prior[-1].attachments = [
        {"kind": "markdown_document", "content": long_md, "title": "Оферта"},
    ]
    source = prior_assistant_source_text(prior)
    assert source is not None
    assert source.strip() == long_md.strip()


def test_attach_on_text_above_in_document():
    offer = "ПУБЛИЧНАЯ ОФЕРТА\n" + "Раздел.\n" * 50
    prior = [_assistant(offer)]
    assert should_attach_prior_material("Сгенерируй текст выше в документ", prior)
    out = build_doc_gen_user_message("Сгенерируй текст выше в документ", prior)
    assert "ПУБЛИЧНАЯ ОФЕРТА" in out
