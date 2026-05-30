"""Роутинг галереи картинок сущности."""

from app.services.entity_image_routing import build_entity_image_query, wants_entity_images


def test_wants_entity_images_positive():
    assert wants_entity_images("Расскажи про питбуля")
    assert wants_entity_images("расскажип про питбуля")
    assert wants_entity_images("Что такое Колизей")
    assert wants_entity_images("Расскажите о Риме", intent="factual_current")


def test_wants_entity_images_negative():
    assert not wants_entity_images("Напиши макрос для Excel", intent="howto")
    assert not wants_entity_images("Курс доллара сегодня")
    assert not wants_entity_images("Привет", intent="chitchat")
    assert not wants_entity_images("Напиши функцию на Python", intent="howto")


def test_image_display_request():
    assert wants_entity_images("Покажи фото собаки колли")
    assert wants_entity_images("Покажи питбуля")
    assert wants_entity_images("покажи мне Рим")
    assert not wants_entity_images("Покажи как написать макрос в Excel", intent="howto")


def test_build_entity_image_query():
    assert build_entity_image_query("Расскажи про питбуля") == "питбуля"
    assert build_entity_image_query("расскажип про питбуля") == "питбуля"
    assert build_entity_image_query("Покажи фото Рима") == "Рима"
    assert build_entity_image_query("Покажи питбуля") == "питбуля"
    assert build_entity_image_query("покажи мне Рим") == "Рим"
    assert build_entity_image_query("", "fallback query") == "fallback query"
    assert build_entity_image_query("что такое квантовый компьютер") == "квантовый компьютер"
