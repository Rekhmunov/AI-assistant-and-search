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

const SCALES = [1, 1.5, 2, 3];

/** Полноэкранный просмотр фото с зумом и скачиванием. */
export function ImageLightboxOverlay({ url, title, onClose, pageUrl }: Props) {
  const src = useProtectedImageSrc(url) ?? url;
  const [scaleIdx, setScaleIdx] = useState(0);
  const scale = SCALES[scaleIdx];
  const imgRef = useRef<HTMLImageElement>(null);
  useBodyScrollLock(true);

  // Keyboard: Escape = close, +/= zoom in, - zoom out, 0 reset
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "+" || e.key === "=") setScaleIdx(i => Math.min(i + 1, SCALES.length - 1));
      if (e.key === "-") setScaleIdx(i => Math.max(i - 1, 0));
      if (e.key === "0") setScaleIdx(0);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleDownload = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!src) return;
    try {
      await downloadImageBlob(src, buildImageFilename(title));
    } catch { /* silent */ }
  }, [src, title]);

  const canZoomIn  = scaleIdx < SCALES.length - 1;
  const canZoomOut = scaleIdx > 0;

  return createPortal(
    <div
      className="image-lightbox-overlay"
      role="presentation"
      onClick={onClose}
    >
      {/* Toolbar */}
      <div
        className="image-lightbox-toolbar"
        onClick={e => e.stopPropagation()}
      >
        {/* Zoom controls */}
        <button
          type="button"
          className="image-lightbox-toolbar-btn"
          disabled={!canZoomOut}
          onClick={() => setScaleIdx(i => Math.max(i - 1, 0))}
          aria-label="Уменьшить"
          title="Уменьшить (−)"
        >
          <ZoomOut width={18} height={18} strokeWidth={2} />
        </button>

        <span className="image-lightbox-zoom-label">{Math.round(scale * 100)}%</span>

        <button
          type="button"
          className="image-lightbox-toolbar-btn"
          disabled={!canZoomIn}
          onClick={() => setScaleIdx(i => Math.min(i + 1, SCALES.length - 1))}
          aria-label="Увеличить"
          title="Увеличить (+)"
        >
          <ZoomIn width={18} height={18} strokeWidth={2} />
        </button>

        {scale !== 1 && (
          <button
            type="button"
            className="image-lightbox-toolbar-btn"
            onClick={() => setScaleIdx(0)}
            aria-label="Исходный размер"
            title="Исходный размер (0)"
          >
            <Maximize2 width={16} height={16} strokeWidth={2} />
          </button>
        )}

        <div className="image-lightbox-toolbar-sep" />

        {/* Download */}
        {src && (
          <button
            type="button"
            className="image-lightbox-toolbar-btn"
            onClick={handleDownload}
            aria-label="Скачать"
            title="Скачать"
          >
            <ArrowDownToLine width={18} height={18} strokeWidth={2} />
          </button>
        )}

        {/* Source link */}
        {pageUrl && pageUrl !== url && (
          <a
            className="image-lightbox-toolbar-btn image-lightbox-toolbar-link"
            href={pageUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Открыть источник"
            onClick={e => e.stopPropagation()}
          >
            ↗
          </a>
        )}

        {/* Close */}
        <button
          type="button"
          className="image-lightbox-toolbar-btn image-lightbox-toolbar-close"
          onClick={e => { e.stopPropagation(); onClose(); }}
          aria-label={t("close")}
          title="Закрыть (Esc)"
        >
          <X width={18} height={18} strokeWidth={2.2} />
        </button>
      </div>

      {/* Image stage */}
      <div
        className="image-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={e => e.stopPropagation()}
      >
        <div
          className="image-lightbox-stage"
          style={{ overflow: scale > 1 ? "auto" : "hidden" }}
        >
          <img
            ref={imgRef}
            src={src ?? undefined}
            alt={title}
            referrerPolicy="no-referrer"
            decoding="sync"
            draggable={false}
            style={{
              transform: `scale(${scale})`,
              transformOrigin: "center center",
              transition: "transform 0.2s ease",
              cursor: scale > 1 ? "move" : "default",
            }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
