"""
Сервис сканирования документов: фото → оптимизированный PDF.
Этапы:
  1. Обнаружение краёв документа (OpenCV contours)
  2. Перспективная коррекция (warpPerspective)
  3. Улучшение изображения (adaptive threshold + denoise)
  4. Упаковка в PDF (img2pdf)
  5. Сжатие PDF (PyMuPDF)
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# Максимальный размер стороны при обработке (px)
_MAX_DIM = 2480  # A4 при 300 dpi


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


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Упорядочивает 4 точки: tl, tr, br, bl."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left
    rect[2] = pts[np.argmax(s)]   # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _find_document_contour(gray: np.ndarray) -> np.ndarray | None:
    """Находит 4 угла документа на изображении."""
    import cv2

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 30, 100)
    edged = cv2.dilate(edged, None, iterations=2)
    edged = cv2.erode(edged, None, iterations=1)

    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            # Убедимся что контур достаточно большой (>10% площади)
            area = cv2.contourArea(approx)
            img_area = gray.shape[0] * gray.shape[1]
            if area > img_area * 0.10:
                return approx.reshape(4, 2).astype("float32")
    return None


def _perspective_correct(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Применяет перспективную коррекцию по 4 точкам."""
    import cv2

    rect = _order_points(pts)
    (tl, tr, br, bl) = rect

    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = max(int(width_a), int(width_b))

    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = max(int(height_a), int(height_b))

    dst = np.array([
        [0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (max_w, max_h))
    return warped


def _enhance_document(image: np.ndarray, mode: str = "auto") -> np.ndarray:
    """
    Улучшает качество документа.
    mode: 'auto' | 'bw' | 'gray' | 'color'
    """
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Денойзинг
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    if mode == "bw":
        # Чёрно-белый режим — лучший для текстовых документов
        enhanced = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 21, 10
        )
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    if mode == "gray":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    # auto: анализируем — если текстовый → bw, иначе цвет с коррекцией
    std_dev = float(np.std(denoised))
    if std_dev < 60:
        # Низкий контраст → вероятно текстовый документ
        enhanced = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 21, 10
        )
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    # Цветной документ — CLAHE + деnoising в цвете
    if len(image.shape) == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        enhanced_lab = cv2.merge([l_ch, a_ch, b_ch])
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    return image


def _resize_if_needed(image: np.ndarray) -> np.ndarray:
    """Уменьшает изображение если оно слишком большое."""
    import cv2

    h, w = image.shape[:2]
    if max(h, w) <= _MAX_DIM:
        return image
    scale = _MAX_DIM / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def process_image_to_scanned(image_bytes: bytes) -> bytes:
    """
    Основной пайплайн: bytes(фото) → bytes(обработанный JPEG).
    Возвращает обработанное изображение.
    """
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ScanError("invalid_image", "Не удалось декодировать изображение")

    image = _resize_if_needed(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Попытка найти контур документа
    contour = _find_document_contour(gray)
    if contour is not None:
        logger.info("scan: document contour found, applying perspective correction")
        image = _perspective_correct(image, contour)
    else:
        logger.info("scan: contour not found, using full image")
        # Без коррекции — просто обрабатываем как есть

    # Улучшение изображения
    enhanced = _enhance_document(image, mode="auto")

    # Кодируем в JPEG с хорошим качеством
    _, jpeg_bytes = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return jpeg_bytes.tobytes()


def images_to_pdf(image_bytes_list: list[bytes]) -> bytes:
    """Упаковывает список JPEG-байтов в PDF через img2pdf."""
    import img2pdf

    return img2pdf.convert(image_bytes_list)


def compress_pdf(pdf_bytes: bytes) -> bytes:
    """Сжимает PDF через PyMuPDF. garbage=2 для лучшей совместимости с мобильными."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    buf = io.BytesIO()
    doc.save(buf, garbage=2, deflate=True)
    doc.close()
    return buf.getvalue()


def scan_images_to_pdf(images: list[bytes]) -> ScanResult:
    """
    Полный пайплайн: список фото → ScanResult с PDF.
    """
    if not images:
        raise ScanError("no_images", "Нет изображений для обработки")

    original_total = sum(len(b) for b in images)

    processed_images: list[bytes] = []
    for i, img_bytes in enumerate(images):
        logger.info("scan: processing page %d/%d", i + 1, len(images))
        processed = process_image_to_scanned(img_bytes)
        processed_images.append(processed)

    # Упаковка в PDF
    pdf_bytes = images_to_pdf(processed_images)

    # Сжатие
    try:
        compressed = compress_pdf(pdf_bytes)
    except Exception as exc:
        logger.warning("scan: PDF compression failed, using uncompressed: %s", exc)
        compressed = pdf_bytes

    return ScanResult(
        pdf_bytes=compressed,
        page_count=len(images),
        original_size_kb=original_total // 1024,
        output_size_kb=len(compressed) // 1024,
    )
