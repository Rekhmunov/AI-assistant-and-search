from app.services.legal_html import sanitize_legal_html


def test_sanitize_strips_script():
    raw = '<p>Hi</p><script>alert(1)</script>'
    out = sanitize_legal_html(raw)
    assert "<script" not in out.lower()
    assert "Hi" in out


def test_sanitize_empty_returns_paragraph():
    assert sanitize_legal_html("") == "<p></p>"
