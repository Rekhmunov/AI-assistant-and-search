"""
Сервис сканирования документов: фото → оптимизированный PDF.
Этапы:
  1. Обнаружение краёв: Hough Lines + findContours (двойная попытка)
  2. Перспективная коррекция (warpPerspective)
  3. Улучшение: Sauvola binarization для текста, CLAHE для цвета
  4. Упаковка в PDF (img2pdf) + сжатие (PyMuPDF)
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

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
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _find_document_contour(gray: np.ndarray) -> np.ndarray | None:
    """
    Двойная попытка найти 4 угла документа:
    1. findContours — быстро, хорошо на тёмном/контрастном фоне
    2. HoughLinesP — лучше на светлом фоне, когда контур не замкнут
    """
    import cv2

    h, w = gray.shape
    img_area = h * w

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 30, 120)
    edged = cv2.dilate(edged, None, iterations=2)
    edged = cv2.erode(edged, None, iterations=1)

    # ── Попытка 1: контурный поиск ──────────────────────────────────────────
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            area = cv2.contourArea(approx)
            if area > img_area * 0.15:
                logger.debug("scan: contour method succeeded")
                return approx.reshape(4, 2).astype("float32")

    # ── Попытка 2: Hough Lines (работает когда фон светлый/пёстрый) ─────────
    min_line_len = int(min(h, w) * 0.25)
    lines = cv2.HoughLinesP(
        edged, 1, np.pi / 180,
        threshold=60,
        minLineLength=min_line_len,
        maxLineGap=20,
    )
    if lines is None or len(lines) < 4:
        return None

    # OpenCV 4: lines shape (N,1,4); OpenCV 5: shape (N,4)
    lines_flat = lines.reshape(-1, 4)
    pts = lines_flat[:, :2].reshape(-1, 2).astype("float32")
    # Добавляем вторые концы отрезков
    pts2 = lines_flat[:, 2:4].reshape(-1, 2).astype("float32")
    pts = np.vstack([pts, pts2])
    hull = cv2.convexHull(pts)
    if hull is None or len(hull) < 4:
        return None

    peri = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.05 * peri, True)
    if len(approx) == 4:
        area = cv2.contourArea(approx)
        if area > img_area * 0.10:
            logger.debug("scan: Hough method succeeded (%d lines)", len(lines))
            return approx.reshape(4, 2).astype("float32")

    # Fallback: 4 крайние точки hull
    pts_hull = hull.reshape(-1, 2).astype("float32")
    tl = pts_hull[np.argmin(pts_hull[:, 0] + pts_hull[:, 1])]
    tr = pts_hull[np.argmax(pts_hull[:, 0] - pts_hull[:, 1])]
    br = pts_hull[np.argmax(pts_hull[:, 0] + pts_hull[:, 1])]
    bl = pts_hull[np.argmin(pts_hull[:, 0] - pts_hull[:, 1])]
    quad = np.array([tl, tr, br, bl], dtype="float32")
    if cv2.contourArea(quad) > img_area * 0.10:
        logger.debug("scan: Hough hull corners used")
        return quad

    return None


def _perspective_correct(image: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Перспективная коррекция по 4 точкам."""
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
    return cv2.warpPerspective(image, M, (max_w, max_h))


def _enhance_document(image: np.ndarray, mode: str = "auto") -> np.ndarray:
    """
    Улучшение качества документа.
    Для текста — Sauvola binarization (лучше adaptive threshold при неравномерном освещении).
    Для цветных документов — CLAHE в LAB-пространстве.
    """
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image

    # Лёгкий денойзинг
    denoised = cv2.fastNlMeansDenoising(gray, h=8)

    if mode == "bw":
        return cv2.cvtColor(_sauvola_binarize(denoised), cv2.COLOR_GRAY2BGR)

    if mode == "gray":
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return cv2.cvtColor(clahe.apply(denoised), cv2.COLOR_GRAY2BGR)

    # auto: определяем тип документа по стандартному отклонению
    std_dev = float(np.std(denoised))
    if std_dev < 65:
        # Текстовый документ — Sauvola (умный адаптивный порог)
        logger.debug("scan: text mode, using Sauvola binarization (std=%.1f)", std_dev)
        return cv2.cvtColor(_sauvola_binarize(denoised), cv2.COLOR_GRAY2BGR)

    # Цветной документ — CLAHE
    logger.debug("scan: color mode, using CLAHE (std=%.1f)", std_dev)
    if len(image.shape) == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        enhanced_lab = cv2.merge([l_ch, a_ch, b_ch])
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    return image


def _sauvola_binarize(gray: np.ndarray) -> np.ndarray:
    """Sauvola binarization с полным fallback на adaptiveThreshold при любой ошибке."""
    import cv2

    def _adaptive() -> np.ndarray:
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
        )

    try:
        from skimage.filters import threshold_sauvola
        h, w = gray.shape[:2]
        win = min(25, (min(h, w) // 4) * 2 + 1)
        if win < 3:
            return _adaptive()
        thresh = threshold_sauvola(gray, window_size=win, k=0.2)
        return (gray > thresh).astype(np.uint8) * 255
    except ImportError:
        logger.warning("scan: scikit-image not available, using adaptiveThreshold")
        return _adaptive()
    except Exception as exc:
        logger.warning("scan: Sauvola failed (%s), fallback to adaptiveThreshold", exc)
        return _adaptive()


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
    """Основной пайплайн: bytes(фото) → bytes(обработанный JPEG)."""
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image is None:
        raise ScanError("invalid_image", "Не удалось декодировать изображение")

    image = _resize_if_needed(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    contour = _find_document_contour(gray)
    if contour is not None:
        logger.info("scan: applying perspective correction")
        image = _perspective_correct(image, contour)
    else:
        logger.info("scan: no contour found, processing full image")

    enhanced = _enhance_document(image, mode="auto")

    ok, jpeg_bytes = cv2.imencode(".jpg", enhanced, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok or jpeg_bytes is None:
        raise ScanError("encode_failed", "Не удалось закодировать изображение")
    return jpeg_bytes.tobytes()


def images_to_pdf(image_bytes_list: list[bytes]) -> bytes:
    """Упаковывает список JPEG-байтов в PDF."""
    import img2pdf
    return img2pdf.convert(image_bytes_list)


def compress_pdf(pdf_bytes: bytes) -> bytes:
    """Сжимает PDF через PyMuPDF. garbage=2 для лучшей совместимости с мобильными."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    buf = io.BytesIO()
    doc.save(buf, garbage=2, deflate=True)
    doc.close()
    return buf.getvalue()


def scan_images_to_pdf(images: list[bytes]) -> ScanResult:
    """Полный пайплайн: список фото → ScanResult с PDF."""
    if not images:
        raise ScanError("no_images", "Нет изображений для обработки")

    original_total = sum(len(b) for b in images)
    processed_images: list[bytes] = []

    for i, img_bytes in enumerate(images):
        logger.info("scan: processing page %d/%d", i + 1, len(images))
        processed = process_image_to_scanned(img_bytes)
        processed_images.append(processed)

    pdf_bytes = images_to_pdf(processed_images)

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
