"""Allowlist HTML sanitization for user-authored rich text."""

from __future__ import annotations

import bleach
from bleach.css_sanitizer import CSSSanitizer

# CSS-свойства, разрешённые в inline-стилях блога
_ALLOWED_CSS_PROPERTIES = [
    # Размеры и отображение
    "width", "min-width", "max-width",
    "height", "min-height", "max-height",
    "display", "float", "clear",
    "vertical-align", "object-fit",
    # Отступы
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    # Оформление
    "text-align", "line-height", "font-size", "font-weight",
    "color", "background-color",
    "border-radius", "border",
]

_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=_ALLOWED_CSS_PROPERTIES)

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
    "*": ["class", "style"],  # style разрешён везде — CSS фильтрует CSSSanitizer
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
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


def _clean(html: str, *, tags: frozenset[str], attrs: dict, empty_default: str, css_sanitizer=None) -> str:
    text = (html or "").strip()
    if not text:
        return empty_default
    cleaned = bleach.clean(
        text,
        tags=tags,
        attributes=attrs,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        css_sanitizer=css_sanitizer,
    )
    return cleaned.strip() or empty_default


def sanitize_rich_html(html: str, *, empty_default: str = "<p></p>") -> str:
    return _clean(html, tags=_BLOG_TAGS, attrs=_BLOG_ATTRS, empty_default=empty_default, css_sanitizer=_CSS_SANITIZER)


def sanitize_legal_rich_html(html: str, *, empty_default: str = "<p></p>") -> str:
    return _clean(html, tags=_LEGAL_TAGS, attrs=_LEGAL_ATTRS, empty_default=empty_default)
