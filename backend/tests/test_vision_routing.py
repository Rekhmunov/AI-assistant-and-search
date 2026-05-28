"""Маршрутизация vision: только фото vs выжимка + поиск."""

from app.services.vision_routing import (
    is_vision_only_user_query,
    wants_web_search_with_vision,
)


def test_empty_query_is_vision_only():
    assert is_vision_only_user_query("")
    assert not wants_web_search_with_vision("")


def test_vision_only_markers():
    assert is_vision_only_user_query("Что на фото?")
    assert not wants_web_search_with_vision("Что на фото?")


def test_search_markers_enable_hybrid():
    assert wants_web_search_with_vision("Найди цену на этот товар на фото")
    assert not is_vision_only_user_query("Найди цену на этот товар на фото")


def test_search_marker_without_vision_only_phrase():
    assert wants_web_search_with_vision("Сколько стоит эта модель?")
    assert not is_vision_only_user_query("Сколько стоит эта модель?")
