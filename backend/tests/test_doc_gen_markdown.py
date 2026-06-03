from app.services.doc_gen_markdown import plain_answer_to_markdown


def test_plain_to_markdown_offer():
    title, md = plain_answer_to_markdown(
        "ПУБЛИЧНАЯ ОФЕРТА\n\nТермины\n1.1. Пункт один.",
        title_hint=None,
    )
    assert "оферт" in title.lower()
    assert "#" in md
    assert "1.1." in md
