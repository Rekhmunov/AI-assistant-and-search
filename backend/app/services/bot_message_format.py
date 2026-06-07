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
_INLINE_ALLOWED = frozenset({"b", "strong", "i", "em", "u", "a", "s", "del", "code", "ins"})
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
    Plain \\n и HTML из редактора (<p>, <br>) → HTML с <br>, иначе MAX склеивает строки.
    """
    text = text.strip()
    if not text:
        return text, text_format

    fmt = text_format or detect_max_text_format(text)
    if fmt == "html" or (fmt is None and _HTML_TAG_RE.search(text)):
        return _normalize_html_for_max(text), "html"
    if fmt == "markdown":
        return text, "markdown"
    if "\n" in text:
        return _plain_newlines_to_max_html(text), "html"
    return text, text_format


def _plain_newlines_to_max_html(text: str) -> str:
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    for para in paragraphs:
        if not para:
            continue
        parts.append("<br>".join(escape(line) for line in para.split("\n")))
    return _collapse_br("<br><br>".join(parts))


def _collapse_br(html: str) -> str:
    html = re.sub(r"(?:<br>){3,}", "<br><br>", html)
    html = re.sub(r"^(?:<br>)+", "", html)
    html = re.sub(r"(?:<br>)+$", "", html)
    return html.strip()


class _MaxHtmlNormalizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def _tail(self) -> str:
        return "".join(self._out[-4:])

    def _append_para_break(self) -> None:
        if not self._out:
            return
        if self._tail().endswith("<br><br>") or self._tail().endswith("<br>"):
            if self._out[-1] == "<br>":
                self._out.append("<br>")
            return
        self._out.append("<br><br>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._out.append("<br>")
            return
        if tag in _BLOCK_TAGS:
            self._append_para_break()
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href" and v), "")
            if href:
                self._out.append(f'<a href="{escape(href, quote=True)}">')
            return
        if tag in _INLINE_ALLOWED:
            self._out.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCK_TAGS:
            if self._out and self._out[-1] != "<br>":
                self._out.append("<br><br>")
            elif self._out and self._out[-1] == "<br>":
                self._out.append("<br>")
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            self._out.append("</a>")
            return
        if tag in _INLINE_ALLOWED:
            self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not data:
            return
        chunk = escape(data).replace("\u00a0", "&nbsp;")
        self._out.append(chunk)


def _normalize_html_for_max(html: str) -> str:
    parser = _MaxHtmlNormalizer()
    parser.feed(html)
    parser.close()
    return _collapse_br("".join(parser._out))
