from app.services.answer_guard import (
    image_display_answer_addon,
    is_source_disclaimer_answer,
    is_template_evasion,
)


def test_image_display_answer_addon_mentions_gallery_not_refusal():
    addon = image_display_answer_addon()
    lower = addon.lower()
    assert "галерея" in lower
    assert "ограничения чата" in lower
    assert "glosix не встраивает" not in lower


def test_is_source_disclaimer_answer_detects_refusal():
    text = (
        "Исходя из предоставленных материалов, прямой информации о напоминаниях нет. "
        "Рекомендую обратиться к документации."
    )
    assert is_source_disclaimer_answer(text)


def test_is_source_disclaimer_answer_allows_long_practical_answer():
    text = (
        "Да, напоминания можно реализовать через webhook и cron. "
        + "Шаги реализации: " + " ".join(["подробность"] * 200)
        + " В источниках не упоминается конкретный лимит API."
    )
    assert not is_source_disclaimer_answer(text)


def test_template_evasion_includes_source_disclaimer():
    text = "В источниках нет информации о данной функции."
    assert is_template_evasion(text)
