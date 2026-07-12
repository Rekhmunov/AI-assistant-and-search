"""
Сервис сканирования документов: фото → PDF через AI (NanaBanana/GigaChat).
AI обрабатывает изображение: выравнивает перспективу, убирает тени, улучшает чёткость.
Результат упаковывается в PDF через img2pdf.

Fallback:
  - image_gen_provider = nanab2 → упадёт → пробует gigachat
  - image_gen_provider = gigachat → упадёт → пробует nanab2
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
    provider_id: str,
    settings,
) -> bytes:
    """
    Обрабатывает фото документа через AI.
    Возвращает байты улучшенного изображения.
    Если основной провайдер упал — пробует резервный.
    """
    from app.services.gigachat_image_gen import ImageGenerationError

    providers_to_try = _get_provider_order(provider_id)

    last_error: Exception | None = None
    for pid in providers_to_try:
        try:
            result = await _call_provider(pid, image_bytes, settings)
            logger.info("scan_ai: success via provider=%s", pid)
            return result
        except ImageGenerationError as exc:
            logger.warning("scan_ai: provider=%s failed: %s", pid, exc)
            last_error = exc
            continue
        except Exception as exc:
            logger.warning("scan_ai: provider=%s unexpected error: %s", pid, exc)
            last_error = exc
            continue

    raise ScanError(
        "provider_unavailable",
        f"Не удалось обработать изображение: {last_error}",
    )


def _get_provider_order(primary: str) -> list[str]:
    """
    Сканирование требует img2img — только NanaBanana поддерживает.
    GigaChat — text2image, не поддерживает редактирование фото документа.
    """
    return ["nanab2"]


async def _call_provider(provider_id: str, image_bytes: bytes, settings) -> bytes:
    """Вызывает конкретный AI-провайдер для обработки изображения."""
    from app.services.gigachat_image_gen import ImageGenerationError

    if provider_id == "nanab2":
        return await _process_via_nanabanana(image_bytes, settings)
    elif provider_id == "gigachat":
        return await _process_via_gigachat(image_bytes, settings)
    raise ImageGenerationError("provider_unavailable", f"Провайдер {provider_id} неизвестен")


async def _process_via_nanabanana(image_bytes: bytes, settings) -> bytes:
    """Обрабатывает через Nano Banana (Gemini img2img)."""
    from app.services.nano_banana import generate_nano_banana_image
    from app.services.gigachat_image_gen import ImageGenerationError

    if not settings.google_configured:
        raise ImageGenerationError("provider_unavailable", "GOOGLE_API_KEY не настроен")

    result = await generate_nano_banana_image(
        _SCAN_PROMPT,
        api_key=settings.google_api_key,
        input_images=[image_bytes],
        image_size="1K",
    )
    if not result.image_bytes:
        raise ImageGenerationError("empty_response", "Nano Banana не вернул изображение")
    return result.image_bytes


async def _process_via_gigachat(image_bytes: bytes, settings) -> bytes:
    """Обрабатывает через GigaChat image generation."""
    from app.services.gigachat_image_gen import generate_gigachat_image, ImageGenerationError

    if not settings.gigachat_configured:
        raise ImageGenerationError("provider_unavailable", "GIGACHAT_CREDENTIALS не настроен")

    # GigaChat img2img: передаём изображение как base64 в промпте
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        f"<img>{b64}</img>\n"
        "Обработай это фото документа как профессиональный сканер: "
        "выровняй перспективу, убери тени, сделай текст чётким и контрастным, "
        "белый фон и чёрный текст."
    )
    result = await generate_gigachat_image(prompt, settings=settings)
    if not result or not result.image_bytes:
        raise ImageGenerationError("empty_response", "GigaChat не вернул изображение")
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
