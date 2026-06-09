from app.services.document_answer_enforce import (
    ensure_markdown_document_answer,
    has_markdown_document_fence,
)
from app.services.doc_gen_context import refers_to_prior_answer as ctx_refers


def test_refers_to_prior_new_document_negative():
    assert not ctx_refers("Сделай документ с характеристикой Yandex GPT 5")
    assert not ctx_refers("Сгенерируй документ оферту для сервиса")
    assert ctx_refers("Сгенерируй текст выше в документ")
    assert ctx_refers("Оформи ответ выше в markdown")


def test_has_markdown_fence():
    assert has_markdown_document_fence("```markdown\n# Title\n```")
    assert not has_markdown_document_fence("Просто текст")


def test_ensure_wraps_long_document_answer():
    body = "# Характеристики\n\n" + "Строка описания.\n" * 30
    wrapped, changed = ensure_markdown_document_answer(
        body, "Сделай документ с характеристикой Yandex GPT 5"
    )
    assert changed
    assert "```markdown" in wrapped
