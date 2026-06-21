"""Сжатие PDF через Ghostscript."""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Ghostscript профили
_GS_PROFILES: dict[str, str] = {
    "screen": "/screen",   # Максимальное сжатие, 72 dpi
    "ebook": "/ebook",     # Оптимальное, 150 dpi
    "printer": "/printer", # Минимальное, 300 dpi
}

_LEVEL_MAP: dict[str, str] = {
    "screen": "screen",
    "ebook": "ebook",
    "printer": "printer",
}


def detect_compression_level(text: str) -> str:
    """Определяет уровень сжатия из произвольного текста пользователя."""
    t = (text or "").lower()
    if any(w in t for w in ("максимальн", "максимум", "сильн", "screen", "первый", "1")):
        return "screen"
    if any(w in t for w in ("минимальн", "качеств", "лучш", "printer", "печат", "третий", "3")):
        return "printer"
    return "ebook"


def has_explicit_compression_level(text: str) -> bool:
    """Проверяет, указал ли пользователь уровень сжатия явно."""
    t = (text or "").lower()
    return any(w in t for w in (
        "максимальн", "максимум", "сильн", "screen",
        "минимальн", "качеств", "лучш", "printer", "печат",
        "оптимальн", "рекоменд", "оптим", "ebook",
        "первый", "второй", "третий", "1", "2", "3",
    ))


def compress_pdf_bytes(data: bytes, level: str = "ebook") -> bytes:
    """
    Сжимает PDF-байты через Ghostscript.
    level: 'screen' | 'ebook' | 'printer'
    Возвращает сжатые байты или бросает RuntimeError.
    """
    profile = _GS_PROFILES.get(level, "/ebook")

    tmp_in = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_out_path = tmp_in.name + "_compressed.pdf"
    try:
        tmp_in.write(data)
        tmp_in.flush()
        tmp_in.close()

        result = subprocess.run(
            [
                "gs",
                "-dNOPAUSE",
                "-dBATCH",
                "-dQUIET",
                f"-dPDFSETTINGS={profile}",
                "-sDEVICE=pdfwrite",
                f"-sOutputFile={tmp_out_path}",
                tmp_in.name,
            ],
            timeout=120,
            capture_output=True,
        )

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[:500]
            logger.warning("gs failed code=%d: %s", result.returncode, err)
            raise RuntimeError(f"Ghostscript error (code {result.returncode})")

        if not os.path.exists(tmp_out_path):
            raise RuntimeError("Ghostscript did not produce output file")

        with open(tmp_out_path, "rb") as f:
            return f.read()

    finally:
        try:
            os.unlink(tmp_in.name)
        except OSError:
            pass
        try:
            os.unlink(tmp_out_path)
        except OSError:
            pass


def ghostscript_available() -> bool:
    """Проверяет наличие gs в системе."""
    try:
        result = subprocess.run(["gs", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} МБ"
    return f"{size_bytes / 1024:.0f} КБ"
