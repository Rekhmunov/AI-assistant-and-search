import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X, ZoomIn, ZoomOut, Maximize2, ArrowDownToLine } from "lucide-react";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { useProtectedImageSrc } from "../hooks/useProtectedImageSrc";
import { t } from "../i18n";
import { downloadImageBlob, buildImageFilename } from "../lib/downloadImage";

type Props = {
  url: string;
  title: string;
  onClose: () => void;
  pageUrl?: string;
};

const MIN_SCALE = 1;
const MAX_SCALE = 6;

/** Полноэкранный просмотр фото: pinch-to-zoom + кнопки + скачивание. */
export function ImageLightboxOverlay({ url, title, onClose, pageUrl }: Props) {
  const src = useProtectedImageSrc(url) ?? url;

  // scale — текущий масштаб (может быть любым, не только из SCALE_STEPS)
  const [scale, setScale]   = useState(1);
  // translate — смещение при зуме пальцами
  const [tx, setTx]         = useState(0);
  const [ty, setTy]         = useState(0);

  const stageRef  = useRef<HTMLDivElement>(null);
  const imgRef    = useRef<HTMLImageElement>(null);

  // touch-зум: сохраняем начальные значения жеста
  const pinchRef = useRef<{
    dist0: number;
    scale0: number;
    cx: number;   // центр pinch в координатах стейджа
    cy: number;
    tx0: number;
    ty0: number;
  } | null>(null);

  useBodyScrollLock(true);

  // Закрытие по Escape, зум клавишами
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "+" || e.key === "=") setScale(s => Math.min(s * 1.5, MAX_SCALE));
      if (e.key === "-") setScale(s => { const ns = s / 1.5; if (ns <= MIN_SCALE) { setTx(0); setTy(0); return MIN_SCALE; } return ns; });
      if (e.key === "0") { setScale(1); setTx(0); setTy(0); }
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Сброс при смене изображения
  useEffect(() => { setScale(1); setTx(0); setTy(0); }, [url]);

  // ── Pinch-to-zoom touch handlers ──────────────────────────────────────────
  const getTouchDist = (t1: React.Touch, t2: React.Touch) =>
    Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const t1 = e.touches[0], t2 = e.touches[1];
      const stage = stageRef.current?.getBoundingClientRect();
      pinchRef.current = {
        dist0: getTouchDist(t1, t2),
        scale0: scale,
        cx: ((t1.clientX + t2.clientX) / 2) - (stage?.left ?? 0),
        cy: ((t1.clientY + t2.clientY) / 2) - (stage?.top  ?? 0),
        tx0: tx,
        ty0: ty,
      };
    }
  }, [scale, tx, ty]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2 && pinchRef.current) {
      e.preventDefault();
      const t1 = e.touches[0], t2 = e.touches[1];
      const newDist = getTouchDist(t1, t2);
      const p = pinchRef.current;
      const ratio = newDist / p.dist0;
      const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, p.scale0 * ratio));
      setScale(newScale);
      // При зуме к 1 — сбрасываем смещение
      if (newScale <= MIN_SCALE) { setTx(0); setTy(0); }
    }
  }, []);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (e.touches.length < 2) {
      pinchRef.current = null;
    }
  }, []);

  // Двойной тап — переключение 1x / 2x
  const lastTapRef = useRef(0);
  const handleDoubleTap = useCallback((e: React.TouchEvent) => {
    if (e.touches.length !== 1) return;
    const now = Date.now();
    if (now - lastTapRef.current < 300) {
      e.preventDefault();
      setScale(s => {
        if (s > 1.2) { setTx(0); setTy(0); return 1; }
        return 2.5;
      });
    }
    lastTapRef.current = now;
  }, []);

  // Кнопочный зум
  const btnZoomIn  = () => setScale(s => Math.min(s * 1.5, MAX_SCALE));
  const btnZoomOut = () => {
    setScale(s => {
      const ns = s / 1.5;
      if (ns <= MIN_SCALE) { setTx(0); setTy(0); return MIN_SCALE; }
      return ns;
    });
  };
  const btnReset   = () => { setScale(1); setTx(0); setTy(0); };

  const handleDownload = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!src) return;
    try { await downloadImageBlob(src, buildImageFilename(title)); } catch { /* silent */ }
  }, [src, title]);

  const isZoomed = scale > 1.05;
  const scaleLabel = `${Math.round(scale * 100)}%`;

  return createPortal(
    <div
      className="image-lightbox-overlay"
      role="presentation"
      onClick={isZoomed ? undefined : onClose}
    >
      {/* ── Toolbar ── */}
      <div className="image-lightbox-toolbar" onClick={e => e.stopPropagation()}>
        <button type="button" className="image-lightbox-toolbar-btn"
          disabled={!isZoomed} onClick={btnZoomOut} aria-label="Уменьшить" title="Уменьшить (−)">
          <ZoomOut width={18} height={18} strokeWidth={2} />
        </button>

        <span className="image-lightbox-zoom-label">{scaleLabel}</span>

        <button type="button" className="image-lightbox-toolbar-btn"
          disabled={scale >= MAX_SCALE} onClick={btnZoomIn} aria-label="Увеличить" title="Увеличить (+)">
          <ZoomIn width={18} height={18} strokeWidth={2} />
        </button>

        {isZoomed && (
          <button type="button" className="image-lightbox-toolbar-btn"
            onClick={btnReset} aria-label="Исходный размер" title="Исходный размер (0)">
            <Maximize2 width={16} height={16} strokeWidth={2} />
          </button>
        )}

        <div className="image-lightbox-toolbar-sep" />

        {src && (
          <button type="button" className="image-lightbox-toolbar-btn"
            onClick={handleDownload} aria-label="Скачать" title="Скачать">
            <ArrowDownToLine width={18} height={18} strokeWidth={2} />
          </button>
        )}

        {pageUrl && pageUrl !== url && (
          <a className="image-lightbox-toolbar-btn image-lightbox-toolbar-link"
            href={pageUrl} target="_blank" rel="noopener noreferrer"
            title="Открыть источник" onClick={e => e.stopPropagation()}>↗</a>
        )}

        <button type="button"
          className="image-lightbox-toolbar-btn image-lightbox-toolbar-close"
          onClick={e => { e.stopPropagation(); onClose(); }}
          aria-label={t("close")} title="Закрыть (Esc)">
          <X width={18} height={18} strokeWidth={2.2} />
        </button>
      </div>

      {/* ── Image stage ── */}
      <div
        className="image-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={e => e.stopPropagation()}
      >
        <div
          ref={stageRef}
          className="image-lightbox-stage"
          style={{
            overflow: isZoomed ? "auto" : "hidden",
            touchAction: isZoomed ? "pan-x pan-y" : "none",
          }}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          // двойной тап
          onTouchStartCapture={handleDoubleTap}
        >
          <img
            ref={imgRef}
            src={src ?? undefined}
            alt={title}
            referrerPolicy="no-referrer"
            decoding="sync"
            draggable={false}
            style={{
              transform: `scale(${scale}) translate(${tx}px, ${ty}px)`,
              transformOrigin: "center center",
              transition: pinchRef.current ? "none" : "transform 0.15s ease",
              cursor: isZoomed ? "grab" : "default",
              // При зуме позволяем картинке быть больше контейнера
              maxWidth: isZoomed ? `${scale * 100}%` : "100%",
              maxHeight: isZoomed ? "none" : "calc(90vh - 96px)",
            }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
