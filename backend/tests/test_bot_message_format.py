from app.services.bot_message_format import (
    MAX_MESSAGE_TEXT_LIMIT,
    _MD_SOFT_BREAK,
    detect_max_text_format,
    prepare_max_message,
    truncate_max_message_text,
)


def test_detect_html_format():
    assert detect_max_text_format("<p>Привет <b>мир</b></p>") == "html"


def test_detect_markdown_format():
    assert detect_max_text_format("Привет **мир**") == "markdown"
    assert detect_max_text_format("Сайт [Glosix](https://glosix.ru)") == "markdown"


def test_plain_text_no_format():
    assert detect_max_text_format("Простой текст без разметки") is None


def test_plain_newlines_use_markdown_hard_breaks():
    text, fmt = prepare_max_message("Строка один\nСтрока два")
    assert fmt == "markdown"
    assert text == f"Строка один{_MD_SOFT_BREAK}Строка два"


def test_plain_paragraph_breaks_use_markdown():
    text, fmt = prepare_max_message("Абзац один\n\nАбзац два")
    assert fmt == "markdown"
    assert text == "Абзац один\n\nАбзац два"


def test_editor_html_converts_to_markdown_with_breaks():
    html = "<p>Первая строка<br>Вторая строка</p><p>Новый абзац</p>"
    text, fmt = prepare_max_message(html)
    assert fmt == "markdown"
    assert "<" not in text
    assert f"Первая строка{_MD_SOFT_BREAK}Вторая строка" in text
    assert "Новый абзац" in text
    assert text.index("Вторая строка") < text.index("Новый абзац")


def test_editor_div_blocks_use_markdown_paragraphs():
    html = "<div>Строка 1</div><div>Строка 2</div>"
    text, fmt = prepare_max_message(html)
    assert fmt == "markdown"
    assert "Строка 1" in text
    assert "Строка 2" in text
    assert "\n\n" in text


def test_editor_html_keeps_bold_and_maps_underline_to_markdown():
    text, fmt = prepare_max_message("<p>Привет <b>мир</b> и <u>подчёркнуто</u></p>")
    assert fmt == "markdown"
    assert "**мир**" in text
    assert "++подчёркнуто++" in text


def test_editor_link_converts_to_markdown():
    text, fmt = prepare_max_message('<p>Читайте <a href="https://glosix.ru">сайт</a></p>')
    assert fmt == "markdown"
    assert "[сайт](https://glosix.ru)" in text


def test_prepare_max_message_truncates_to_4000():
    long_text = "x" * 5000
    text, _fmt = prepare_max_message(long_text)
    assert len(text) <= MAX_MESSAGE_TEXT_LIMIT


def test_truncate_max_message_text():
    assert len(truncate_max_message_text("a" * 5000)) <= MAX_MESSAGE_TEXT_LIMIT


def test_explicit_html_format_uses_br_tags():
    html = "<p>Строка 1<br>Строка 2</p>"
    text, fmt = prepare_max_message(html, text_format="html")
    assert fmt == "html"
    assert "<br/>" in text
    assert "Строка 1" in text and "Строка 2" in text
