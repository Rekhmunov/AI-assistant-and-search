from app.services.bot_message_format import detect_max_text_format


def test_detect_html_format():
    assert detect_max_text_format("<p>Привет <b>мир</b></p>") == "html"


def test_detect_markdown_format():
    assert detect_max_text_format("Привет **мир**") == "markdown"
    assert detect_max_text_format("Сайт [Glosix](https://glosix.ru)") == "markdown"


def test_plain_text_no_format():
    assert detect_max_text_format("Простой текст без разметки") is None
