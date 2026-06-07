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


def test_plain_newlines_use_markdown_format():
    text, fmt = prepare_max_message("Строка один\nСтрока два")
    assert fmt == "markdown"
    assert text == "Строка один\nСтрока два"


def test_plain_paragraph_breaks_use_markdown():
    text, fmt = prepare_max_message("Абзац один\n\nАбзац два")
    assert fmt == "markdown"
    assert text == "Абзац один\n\nАбзац два"


def test_editor_html_uses_newlines_not_br_tags():
    html = "<p>Первая строка<br>Вторая строка</p><p>Новый абзац</p>"
    text, fmt = prepare_max_message(html)
    assert fmt == "html"
    assert "<br" not in text.lower()
    assert "Первая строка\nВторая строка" in text
    assert "Новый абзац" in text
    assert text.index("Вторая строка") < text.index("Новый абзац")


def test_editor_div_blocks_use_newlines():
    html = "<div>Строка 1</div><div>Строка 2</div>"
    text, fmt = prepare_max_message(html)
    assert fmt == "html"
    assert "Строка 1" in text
    assert "Строка 2" in text
    assert "\n" in text


def test_editor_html_keeps_bold_and_maps_underline():
    text, fmt = prepare_max_message("<p>Привет <b>мир</b> и <u>подчёркнуто</u></p>")
    assert fmt == "html"
    assert "<b>мир</b>" in text
    assert "<ins>подчёркнуто</ins>" in text
    assert "<u>" not in text
