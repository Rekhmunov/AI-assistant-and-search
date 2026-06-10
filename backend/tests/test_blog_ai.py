import pytest

from app.services.blog_ai import _HTML_DELIM, _META_DELIM, _parse_json_blob


def test_parse_delimiter_format():
    raw = f"""{_META_DELIM}
{{"title":"Заголовок","excerpt":"Кратко","meta_title":"SEO","meta_description":"Desc","meta_keywords":"a,b","og_title":"OG","og_description":"OGD"}}
{_HTML_DELIM}
<p>Текст</p><h2>Раздел</h2>"""
    data = _parse_json_blob(raw)
    assert data["title"] == "Заголовок"
    assert "<h2>Раздел</h2>" in data["content_html"]


def test_parse_json_with_html_quotes():
    raw = """```json
{
  "title": "Test",
  "excerpt": "E",
  "content_html": "<p>He said \\"hi\\"</p>",
  "meta_title": "T",
  "meta_description": "D",
  "meta_keywords": "k",
  "og_title": "O",
  "og_description": "OD"
}
```"""
    data = _parse_json_blob(raw)
    assert data["title"] == "Test"
    assert "hi" in data["content_html"]


def test_parse_delimiter_with_preamble_and_spaced_markers():
    raw = f"""Вот статья:

--- META ---
{{"title":"Заголовок","excerpt":"Кратко","meta_title":"SEO","meta_description":"Desc","meta_keywords":"a,b","og_title":"OG","og_description":"OGD"}}
--- HTML ---
<p>Текст</p>"""
    data = _parse_json_blob(raw)
    assert data["title"] == "Заголовок"
    assert "Текст" in data["content_html"]


def test_parse_delimiter_with_broken_json_uses_fallback():
    raw = f"""{_META_DELIM}
{{"title":"Заголовок","excerpt":"Кратко","meta_title":"SEO"
{_HTML_DELIM}
<p>Текст</p>"""
    data = _parse_json_blob(raw)
    assert data["title"] == "Заголовок"
    assert "Текст" in data["content_html"]


def test_parse_json_with_trailing_comma():
    raw = """{"title":"T","excerpt":"E","content_html":"<p>x</p>","meta_title":"M","meta_description":"D","meta_keywords":"k","og_title":"O","og_description":"OD",}"""
    data = _parse_json_blob(raw)
    assert data["title"] == "T"
    assert "x" in data["content_html"]


def test_parse_invalid_raises():
    with pytest.raises(Exception):
        _parse_json_blob("not json at all")
