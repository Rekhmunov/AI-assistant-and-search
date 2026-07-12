"""
Сервис сканирования документов: фото → PDF через AI (NanaBanana / Gemini img2img).
NanaBanana — единственный поддерживаемый провайдер (img2img редактирование).
Результат упаковывается в PDF через img2pdf.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SCAN_PROMPT = (
    "This is a photo of a document. Please process it as a professional document scanner would:\n"
    "1. Straighten the perspective so the document appears flat and rectangular\n"
    "2. Remove shadows and uneven lighting\n"
    "3. Enhance text contrast — make text sharp, dark and clearly readable\n"
    "4. Produce a clean white background with black text\n"
    "5. Keep the full document visible without cropping any content\n"
    "Return only the processed document image, nothing else."
)


@dataclass
class ScanResult:
    pdf_bytes: bytes
    page_count: int
    original_size_kb: int
    output_size_kb: int


class ScanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


async def process_image_with_ai(
    image_bytes: bytes,
    *,
    settings,
) -> bytes:
    """
    Обрабатывает фото документа через NanaBanana (Gemini img2img).
    Возвращает байты улучшенного изображения.
    """
    from app.services.gigachat_image_gen import ImageGenerationError

    if not settings.google_configured:
        raise ScanError("provider_unavailable", "GOOGLE_API_KEY не настроен. Сканирование недоступно.")

    try:
        result = await _call_nanabanana(image_bytes, settings)
        logger.info("scan_ai: success via NanaBanana")
        return result
    except ImageGenerationError as exc:
        raise ScanError(exc.code if hasattr(exc, "code") else "api_error", str(exc)) from exc
    except ScanError:
        raise
    except Exception as exc:
        raise ScanError("scan_failed", f"Ошибка при обработке изображения: {exc}") from exc


async def _call_nanabanana(image_bytes: bytes, settings) -> bytes:
    """Вызывает Nano Banana (Gemini) для img2img обработки документа."""
    from app.services.nano_banana import generate_nano_banana_image
    from app.services.gigachat_image_gen import ImageGenerationError

    result = await generate_nano_banana_image(
        _SCAN_PROMPT,
        api_key=settings.google_api_key,
        input_images=[image_bytes],
        image_size="1K",
    )
    if not result or not result.image_bytes:
        raise ImageGenerationError("empty_response", "NanaBanana не вернул изображение")
    return result.image_bytes


def images_to_pdf(image_bytes_list: list[bytes]) -> bytes:
    """Упаковывает список изображений в PDF через img2pdf."""
    import img2pdf
    return img2pdf.convert(image_bytes_list)


def compress_pdf(pdf_bytes: bytes) -> bytes:
    """Сжимает PDF через PyMuPDF. garbage=2 для совместимости с мобильными."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    buf = io.BytesIO()
    doc.save(buf, garbage=2, deflate=True)
    doc.close()
    return buf.getvalue()
