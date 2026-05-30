from app.services.answer_guard import image_display_answer_addon


def test_image_display_answer_addon_mentions_gallery_not_refusal():
    addon = image_display_answer_addon()
    lower = addon.lower()
    assert "галерея" in lower
    assert "ограничения чата" in lower
    assert "glosix не встраивает" not in lower
