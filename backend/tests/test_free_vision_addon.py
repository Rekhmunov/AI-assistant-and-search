from app.services.answer_guard import free_vision_pro_addon


def test_free_vision_pro_addon_mentions_pro():
    text = free_vision_pro_addon()
    assert "Pro" in text
    assert "распознаван" in text.lower()
