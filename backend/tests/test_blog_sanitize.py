from app.services.blog_sanitize import estimate_reading_time_min, sanitize_blog_html


def test_sanitize_strips_script():
    html = '<p>ok</p><script>alert(1)</script>'
    assert "<script" not in sanitize_blog_html(html)


def test_reading_time():
    html = "<p>" + " слово" * 360 + "</p>"
    assert estimate_reading_time_min(html) >= 2
