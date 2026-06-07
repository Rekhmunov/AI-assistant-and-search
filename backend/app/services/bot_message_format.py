"""Подготовка текста и формата для MAX Bot API (markdown / html, переносы строк)."""

from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser

_HTML_TAG_RE = re.compile(r"<[a-z][\s\S]*?>", re.IGNORECASE)
_MARKDOWN_RE = re.compile(
    r"(\*\*.+\*\*|__.+__|~~.+~~|\+\+.+?\+\+|\[.+\]\([^)]+\)|`[^`]+`|\^\^.+?\^\^)",
    re.DOTALL,
)

_BLOCK_TAGS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"})
_LIST_TAGS = frozenset({"ul", "ol"})
_INLINE_MD = {
    "b": ("**", "**"),
    "strong": ("**", "**"),
    "i": ("*", "*"),
    "em": ("*", "*"),
    "u": ("++", "++"),
    "ins": ("++", "++"),
    "del": ("~~", "~~"),
    "s": ("~~", "~~"),
    "code": ("`", "`"),
}
_STRIP_TAGS = frozenset({"font", "span"})

# Markdown hard line break: два пробела перед переводом строки (dev.max.ru, раздел Markdown).
_MD_SOFT_BREAK = "  \n"


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

    HTML из редактора и plain-текст с переносами → format=markdown:
    - абзац: пустая строка (\\n\\n);
    - строка внутри абзаца: два пробела + \\n (hard break в Markdown).
    Явный text_format=html оставляем для обратной совместимости (<br/>).
    """
    text = text.strip()
    if not text:
        return text, text_format

    if text_format == "html":
        return _html_to_max_html(text), "html"

    if text_format == "markdown":
        return _plain_newlines_to_max_markdown(text), "markdown"

    fmt = text_format or detect_max_text_format(text)
    if fmt == "html" or _HTML_TAG_RE.search(text):
        return _html_to_max_markdown(text), "markdown"

    if fmt == "markdown" or "\n" in text:
        return _plain_newlines_to_max_markdown(text), "markdown"

    return text, text_format


def _plain_newlines_to_max_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    paragraphs = text.split("\n\n")
    parts: list[str] = []
    for para in paragraphs:
        if not para.strip():
            continue
        lines = [line.strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue
        parts.append(_MD_SOFT_BREAK.join(lines))
    return "\n\n".join(parts)


def _normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _HtmlToMaxMarkdown(HTMLParser):
    """HTML из contentEditable → Markdown для MAX (format=markdown)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._list_depth = 0
        self._link_href = ""

    def _append(self, chunk: str) -> None:
        if chunk:
            self._out.append(chunk)

    def _tail(self) -> str:
        return "".join(self._out[-3:])

    def _append_soft_break(self) -> None:
        if self._tail().endswith(_MD_SOFT_BREAK) or self._tail().endswith("\n\n"):
            return
        self._append(_MD_SOFT_BREAK)

    def _append_paragraph_break(self) -> None:
        if not self._out:
            return
        if self._tail().endswith("\n\n"):
            return
        if self._tail().endswith(_MD_SOFT_BREAK):
            self._append("\n")
            return
        self._append("\n\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._append_soft_break()
            return
        if tag in _LIST_TAGS:
            self._list_depth += 1
            return
        if tag == "li":
            self._append_paragraph_break()
            self._append("- ")
            return
        if tag in _BLOCK_TAGS:
            self._append_paragraph_break()
            if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
                level = int(tag[1])
                self._append("#" * min(level, 3) + " ")
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            href = next((v for k, v in attrs if k.lower() == "href" and v), "")
            if href:
                self._link_href = href
                self._append("[")
            return
        if tag in _INLINE_MD:
            self._append(_INLINE_MD[tag][0])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _LIST_TAGS:
            self._list_depth = max(0, self._list_depth - 1)
            self._append_paragraph_break()
            return
        if tag == "li":
            self._append_soft_break()
            return
        if tag in _BLOCK_TAGS:
            self._append_paragraph_break()
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            if self._link_href:
                self._append(f"]({self._link_href})")
            self._link_href = ""
            return
        if tag in _INLINE_MD:
            self._append(_INLINE_MD[tag][1])

    def handle_data(self, data: str) -> None:
        if data:
            self._append(unescape(data).replace("\u00a0", " "))

    def get_result(self) -> str:
        return _normalize_newlines("".join(self._out))


class _HtmlToMaxHtml(HTMLParser):
    """HTML из редактора → HTML для MAX (format=html), переносы через <br/>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def _append(self, chunk: str) -> None:
        if chunk:
            self._out.append(chunk)

    def _append_break(self, *, paragraph: bool = False) -> None:
        if not self._out:
            return
        tail = "".join(self._out[-2:])
        if paragraph:
            if tail.endswith("<br/><br/>") or tail.endswith("<br/>"):
                if not tail.endswith("<br/><br/>"):
                    self._append("<br/>")
                return
            self._append("<br/><br/>")
            return
        if tail.endswith("<br/>"):
            return
        self._append("<br/>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._append_break()
            return
        if tag in _BLOCK_TAGS or tag == "li":
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
                self._append(f'<a href="{escape(href, quote=True)}">')
            return
        if tag in {"b", "strong", "i", "em", "del", "s", "ins", "code", "pre"}:
            self._append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _BLOCK_TAGS or tag == "li":
            self._append_break(paragraph=True)
            return
        if tag in _STRIP_TAGS:
            return
        if tag == "a":
            self._append("</a>")
            return
        if tag == "u":
            self._append("</ins>")
            return
        if tag in {"b", "strong", "i", "em", "del", "s", "ins", "code", "pre"}:
            self._append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if data:
            self._append(escape(unescape(data)).replace("\u00a0", " "))

    def get_result(self) -> str:
        result = "".join(self._out)
        result = re.sub(r"(?:<br/>){3,}", "<br/><br/>", result)
        return result.strip()


def _html_to_max_markdown(html: str) -> str:
    parser = _HtmlToMaxMarkdown()
    parser.feed(html)
    parser.close()
    return parser.get_result()


def _html_to_max_html(html: str) -> str:
    parser = _HtmlToMaxHtml()
    parser.feed(html)
    parser.close()
    return parser.get_result()
