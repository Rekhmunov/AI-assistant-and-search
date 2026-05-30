"""Метаданные картинок сущности для галереи в ответе."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityImage:
    url: str
    title: str
    page_url: str
    width: int | None = None
    height: int | None = None


def entity_images_to_json(images: list[EntityImage]) -> list[dict]:
    return [
        {
            "url": img.url,
            "title": img.title,
            "page_url": img.page_url,
            "width": img.width,
            "height": img.height,
        }
        for img in images
    ]
