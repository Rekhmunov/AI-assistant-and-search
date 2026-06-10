from app.services.html_sanitize import sanitize_legal_rich_html, sanitize_rich_html


def test_strips_script_and_iframe():
    raw = '<p>ok</p><script>alert(1)</script><iframe src="https://evil.test"></iframe>'
    out = sanitize_rich_html(raw)
    assert "<script" not in out.lower()
    assert "<iframe" not in out.lower()
    assert "ok" in out


def test_blocks_javascript_href():
    raw = '<a href="javascript:alert(1)">x</a>'
    out = sanitize_rich_html(raw)
    assert "javascript:" not in out.lower()


def test_allows_safe_link():
    raw = '<a href="https://glosix.ru/blog" rel="noopener">Blog</a>'
    out = sanitize_rich_html(raw)
    assert 'href="https://glosix.ru/blog"' in out


def test_legal_sanitize_empty():
    assert sanitize_legal_rich_html("") == "<p></p>"
