from app.services.bot_message_format import (
    detect_max_text_format,
    prepare_max_message,
)


def test_detect_html_format():
    assert detect_max_text_format("<p>Привет <b>мир</b></p>") == "html"


def test_detect_markdown_format():
    assert detect_max_text_format("Привет **мир**") == "markdown"
    assert detect_max_text_format("Сайт [Glosix](https://glosix.ru)") == "markdown"


def test_plain_text_no_format():
    assert detect_max_text_format("Простой текст без разметки") is None


def test_plain_newlines_become_html_br():
    text, fmt = prepare_max_message("Строка один\nСтрока два")
    assert fmt == "html"
    assert text == "Строка один<br>Строка два"


def test_plain_paragraph_breaks():
    text, fmt = prepare_max_message("Абзац один\n\nАбзац два")
    assert fmt == "html"
    assert text == "Абзац один<br><br>Абзац два"


def test_editor_html_paragraphs_and_line_breaks():
    html = "<p>Первая строка<br>Вторая строка</p><p>Новый абзац</p>"
    text, fmt = prepare_max_message(html)
    assert fmt == "html"
    assert "Первая строка<br>Вторая строка" in text
    assert "Новый абзац" in text
    assert "<p>" not in text
    assert text.index("Вторая строка") < text.index("Новый абзац")


def test_editor_html_keeps_bold():
    text, fmt = prepare_max_message("<p>Привет <b>мир</b></p>")
    assert fmt == "html"
    assert "<b>мир</b>" in text
