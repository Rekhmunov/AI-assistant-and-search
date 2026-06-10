from app.services.blog_seo_meta import clamp_meta_text, get_meta_field_spec, _fallback_meta


def test_meta_title_limit():
    spec = get_meta_field_spec("meta_title")
    assert spec.max_length == 55


def test_meta_description_limit():
    spec = get_meta_field_spec("meta_description")
    assert spec.max_length == 155
    assert spec.min_length == 120


def test_clamp_meta_truncates():
    long = "А" * 80
    out = clamp_meta_text(long, max_len=55)
    assert len(out) <= 55


def test_fallback_meta_title():
    spec = get_meta_field_spec("meta_title")
    out = _fallback_meta("meta_title", "Как работает ИИ-поиск Glosix", "", spec)
    assert len(out) <= 55
    assert "ИИ" in out or "поиск" in out
