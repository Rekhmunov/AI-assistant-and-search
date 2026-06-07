"""Подготовка текста и формата для MAX Bot API (markdown / html, переносы строк)."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.IGNORECASE)
_MARKDOWN_RE = re.compile(
    r"(\*\*.+\*\*|__.+__|~~.+~~|\+\+.+?\+\+|\[.+\]\([^)]+\)|`[^`]+`|\^\^.+?\^\^)",
    re.DOTALL,
)

_BLOCK_TAGS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"})
_INLINE_HTML = frozenset({"b", "strong", "i", "em", "u", "ins", "del", "s", "a", "code", "pre"})
_STRIP_TAGS = frozenset({"font", "span"})


def detect_max_text_format(text: str) -> str | None:
    """Вернуть format для MAX API или None для обычного текста."""
    if _HTML_TAG_RE.search(text):
        return "html"
    if _MARKDOWN_RE.search(text):
        return "markdown"
    return None


def prepare_max_message(text: str, text_format: str | None = None) -> tuple[str, str | None]:
    """
    Нормализовать текст перед отправкой в MAX.

    По документации MAX в HTML-режиме поддерживаются b/i/a/del/ins и т.п., но не <br>.
    Переносы строк — символы \\n в теле сообщения (см. примеры MAX SDK).
    """
    text = text.strip()
    if not text:
        return text, text_format

    if text_format == "markdown":
        return _plain_newlines_to_max_markdown(text), "markdown"

    fmt = text_format or detect_max_text_format(text)
    if fmt == "markdown":
        if "\n" in text:
            return _plain_newlines_to_max_markdown(text), "markdown"
        return text, "markdown"

    if fmt == "html" or _HTML_TAG_RE.search(text):
        return _html_to_max_html(text), "html"

    if "\n" in text:
        return _plain_newlines_to_max_markdown(text), "markdown"

    return text, text_format


def _plain_newlines_to_max_markdown(text: str) -> str:
    """Plain \\n → markdown: абзацы через пустую строку, строки внутри — как есть."""
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    for para in paragraphs:
        if not para:
            continue
        parts.append(para)
    return "\n\n".join(parts)


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _HtmlToMaxText(HTMLParser):
    """HTML из редактора → строка с \\n и поддерживаемыми inline-тегами MAX."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._link_href: str | None = None

    def _append(self, chunk: str) -> None:
        if chunk:
            self._out.append(chunk)

    def _append_break(self, *, paragraph: bool = False) -> None:
        if not self._out:
            return
        tail = "".join(self._out[-2:])
        if tail.endswith("\n\n") or tail.endswith("\n"):
            if paragraph and not tail.endswith("\n\n"):
                self._append("\n")
            return
        self._append("\n\n" if paragraph else "\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._append_break()
            return
        if tag in _BLOCK_TAGS:
            self._append_break(paragraph=True)
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "u":
            self._append("<ins>")
            return
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href" and v), "")
            if href:
                self._link_href = href
                self._append(f'<a href="{escape(href, quote=True)}">')
            return
        if tag in _INLINE_HTML:
            max_tag = "ins" if tag == "u" else tag
            if max_tag in {"b", "strong", "i", "em", "del", "s", "ins", "code", "pre", "a"}:
                self._append(f"<{max_tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCK_TAGS:
            self._append_break(paragraph=True)
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            self._append("</a>")
            self._link_href = None
            return
        if tag in _INLINE_HTML or tag == "u":
            max_tag = "ins" if tag == "u" else tag
            if max_tag in {"b", "strong", "i", "em", "del", "s", "ins", "code", "pre"}:
                self._append(f"</{max_tag}>")

    def handle_data(self, data: str) -> None:
        if data:
            self._append(escape(data).replace("\u00a0", " "))

    def get_result(self) -> str:
        return _normalize_newlines("".join(self._out))


def _html_to_max_html(html: str) -> str:
    parser = _HtmlToMaxText()
    parser.feed(html)
    parser.close()
    return parser.get_result()
