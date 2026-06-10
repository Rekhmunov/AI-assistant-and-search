"""Slug generation: transliterate RU → latin, URL-safe."""

from __future__ import annotations

import re

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def transliterate_to_latin(text: str) -> str:
    out: list[str] = []
    for ch in text.strip().lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif "a" <= ch <= "z" or ch.isdigit():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
        else:
            out.append("-")
    return "".join(out)


def slugify_title(title: str, *, max_len: int = 120) -> str:
    raw = transliterate_to_latin(title)
    raw = re.sub(r"-+", "-", raw).strip("-")
    if not raw:
        raw = "post"
    if len(raw) > max_len:
        raw = raw[:max_len].rstrip("-")
    return raw or "post"


def is_valid_slug(slug: str) -> bool:
    return bool(slug) and len(slug) <= 200 and bool(_SLUG_RE.match(slug))


async def ensure_unique_category_slug(db, base_slug: str, *, exclude_id=None) -> str:
    from sqlalchemy import select

    from app.models.blog import BlogCategory

    slug = base_slug
    n = 2
    while True:
        q = select(BlogCategory.id).where(BlogCategory.slug == slug)
        if exclude_id:
            q = q.where(BlogCategory.id != exclude_id)
        existing = await db.scalar(q)
        if not existing:
            return slug
        slug = f"{base_slug}-{n}"
        n += 1
        if n > 200:
            raise ValueError("slug_collision")


async def ensure_unique_post_slug(
    db, base_slug: str, *, locale: str = "ru", exclude_id=None
) -> str:
    from sqlalchemy import select

    from app.models.blog import BlogPost

    slug = base_slug
    n = 2
    while True:
        q = select(BlogPost.id).where(BlogPost.slug == slug, BlogPost.locale == locale)
        if exclude_id:
            q = q.where(BlogPost.id != exclude_id)
        existing = await db.scalar(q)
        if not existing:
            return slug
        slug = f"{base_slug}-{n}"
        n += 1
        if n > 200:
            raise ValueError("slug_collision")
