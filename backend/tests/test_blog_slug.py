from app.services.blog_slug import is_valid_slug, slugify_title, transliterate_to_latin


def test_transliterate_russian():
    assert transliterate_to_latin("Привет мир") == "privet-mir"


def test_slugify_title():
    assert slugify_title("Как работает ИИ-поиск") == "kak-rabotaet-ii-poisk"


def test_is_valid_slug():
    assert is_valid_slug("hello-world")
    assert not is_valid_slug("Hello-World")
    assert not is_valid_slug("bad slug")
