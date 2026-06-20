"""Allowlist HTML sanitization for user-authored rich text."""

from __future__ import annotations

import bleach

_BLOG_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "a",
        "ul",
        "ol",
        "li",
        "h2",
        "h3",
        "h4",
        "blockquote",
        "img",
        "figure",
        "figcaption",
        "pre",
        "code",
        "span",
        "div",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "hr",
    }
)

_BLOG_ATTRS = {
    "*": ["class"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading", "style"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}

_LEGAL_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "a",
        "ul",
        "ol",
        "li",
        "h2",
        "h3",
        "h4",
        "blockquote",
        "span",
        "div",
        "hr",
    }
)

_LEGAL_ATTRS = {
    "*": ["class"],
    "a": ["href", "title", "target", "rel"],
}

_ALLOWED_PROTOCOLS = ("http", "https", "mailto", "")  # "" = relative URLs (/api/blog/media/...)


def _clean(html: str, *, tags: frozenset[str], attrs: dict, empty_default: str) -> str:
    text = (html or "").strip()
    if not text:
        return empty_default
    cleaned = bleach.clean(
        text,
        tags=tags,
        attributes=attrs,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return cleaned.strip() or empty_default


def sanitize_rich_html(html: str, *, empty_default: str = "<p></p>") -> str:
    return _clean(html, tags=_BLOG_TAGS, attrs=_BLOG_ATTRS, empty_default=empty_default)


def sanitize_legal_rich_html(html: str, *, empty_default: str = "<p></p>") -> str:
    return _clean(html, tags=_LEGAL_TAGS, attrs=_LEGAL_ATTRS, empty_default=empty_default)
