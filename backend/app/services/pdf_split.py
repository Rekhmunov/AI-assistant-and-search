"""Разбивка PDF на части через pypdf."""
from __future__ import annotations

import io
import re

_DEFAULT_PAGES_PER_FILE = 1


def detect_split_params(text: str) -> dict:
    """
    Определяет параметры разбивки из текста запроса.

    Возвращает dict с одним из ключей:
      pages_per_file: int  — по N страниц на файл
      n_parts: int         — разбить на N равных частей

    Примеры:
      «по 10 страниц»     → {pages_per_file: 10}
      «каждые 5 страниц»  → {pages_per_file: 5}
      «на 5 частей»       → {n_parts: 5}
      «на 3 файла»        → {n_parts: 3}
      «пополам»           → {n_parts: 2}
      «на страницы»       → {pages_per_file: 1}
    """
    t = (text or "").lower()

    # «пополам» / «на две части»
    if "пополам" in t or "на две части" in t or "на 2 части" in t or "на 2 файла" in t:
        return {"n_parts": 2}

    # «на страницы» / «каждую страницу» — по 1 странице
    if re.search(r"на\s+(отдельные\s+)?страниц|каждую\s+страниц|по\s+1\s+страниц", t):
        return {"pages_per_file": 1}

    # «по N страниц» / «каждые N страниц»
    m = re.search(
        r"(?:по|каждые?|каждых)\s+(\d+)\s+(?:страниц|стр)",
        t,
    )
    if m:
        n = int(m.group(1))
        if 1 <= n <= 10000:
            return {"pages_per_file": n}

    # «на N частей» / «на N файлов» / «N частей»
    m = re.search(
        r"на\s+(\d+)\s+(?:части|часть|файлов|файла|файл)|(\d+)\s+(?:части|файлов|файла)",
        t,
    )
    if m:
        n = int(m.group(1) or m.group(2))
        if 2 <= n <= 1000:
            return {"n_parts": n}

    # fallback — по 1 странице если просят «разбить» без уточнений
    return {"pages_per_file": _DEFAULT_PAGES_PER_FILE}


def split_pdf_bytes(
    data: bytes,
    *,
    pages_per_file: int | None = None,
    n_parts: int | None = None,
) -> list[tuple[str, bytes]]:
    """
    Разбивает PDF на части.

    Возвращает список (filename, pdf_bytes).
    Использует pypdf — нет системных зависимостей.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(data))
    total = len(reader.pages)

    if total == 0:
        raise ValueError("PDF не содержит страниц")

    # Вычисляем шаг страниц
    if n_parts is not None:
        n_parts = max(2, min(n_parts, total))
        step = max(1, (total + n_parts - 1) // n_parts)
    elif pages_per_file is not None:
        step = max(1, pages_per_file)
    else:
        step = 1

    # Генерируем диапазоны
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < total:
        end = min(start + step, total)
        ranges.append((start, end))
        start = end

    # Количество цифр для нумерации файлов
    digits = len(str(len(ranges)))

    results: list[tuple[str, bytes]] = []
    for i, (s, e) in enumerate(ranges, start=1):
        writer = PdfWriter()
        for page_idx in range(s, e):
            writer.add_page(reader.pages[page_idx])

        buf = io.BytesIO()
        writer.write(buf)
        pdf_bytes = buf.getvalue()

        # Имя: document_001_p1-10.pdf
        page_from = s + 1
        page_to = e
        label = (
            f"p{page_from}"
            if page_from == page_to
            else f"p{page_from}-{page_to}"
        )
        filename = f"part_{str(i).zfill(digits)}_{label}.pdf"
        results.append((filename, pdf_bytes))

    return results


def build_split_zip(parts: list[tuple[str, bytes]]) -> bytes:
    """Упаковывает все части в ZIP-архив."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, pdf_bytes in parts:
            zf.writestr(filename, pdf_bytes)
    return buf.getvalue()
