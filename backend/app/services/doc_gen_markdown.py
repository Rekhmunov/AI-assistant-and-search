"""Преобразование текста ответа в markdown для блока в чате."""

from __future__ import annotations

import re

from app.services.doc_gen_plain import _SOURCE_CHIP_LINE_RE

_SECTION_NUM_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
_SECTION_TITLE_RE = re.compile(
    r"(?i)^(?:термины|предмет|порядок|права|стоимость|ответственность|персональн|реквизит|особые|заключительн)",
)
_TITLE_LINE_RE = re.compile(
    r"(?i)^(?:публичн\w*\s+оферт|договор|соглашен|заявлен|политик\w*\s+конфиденциальности)",
)


def plain_answer_to_markdown(text: str, *, title_hint: str | None = None) -> tuple[str, str]:
    """
    Возвращает (title, markdown_body).
    Не вызывает LLM — только структурирование готового текста.
    """
    body = (text or "").strip()
    if not body:
        return "Документ", ""

    lines = []
    for raw in body.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            lines.append("")
            continue
        if _SOURCE_CHIP_LINE_RE.fullmatch(s):
            continue
        lines.append(s)

    title = (title_hint or "").strip()
    md_lines: list[str] = []
    prev_blank = True

    for line in lines:
        if not line:
            prev_blank = True
            continue

        if not title and _TITLE_LINE_RE.search(line):
            title = line[:200]
            md_lines.append(f"# {line}")
            prev_blank = False
            continue

        if re.match(r"^\d+\.\d+", line):
            md_lines.append(line)
            prev_blank = False
            continue

        is_section = (
            len(line) <= 80
            and (_SECTION_TITLE_RE.search(line) or (_SECTION_NUM_RE.match(line) and "." not in line[3:]))
            and not line.endswith(".")
        ) or (prev_blank and len(line) <= 60 and line[0].isupper() and _SECTION_TITLE_RE.search(line))

        if is_section and not line.startswith("#"):
            md_lines.append(f"## {line}")
        else:
            md_lines.append(line)
        prev_blank = False

    if not title:
        title = md_lines[0].lstrip("# ").strip()[:200] if md_lines else "Документ"

    markdown = "\n\n".join(
        ln for ln in ("\n".join(md_lines).split("\n\n")) if ln.strip()
    )
    if not markdown:
        markdown = body
    return title, markdown
