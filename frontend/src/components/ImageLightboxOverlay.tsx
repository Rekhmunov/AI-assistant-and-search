import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { useProtectedImageSrc } from "../hooks/useProtectedImageSrc";
import { t } from "../i18n";

type Props = {
  url: string;
  title: string;
  onClose: () => void;
  pageUrl?: string;
};

/** Полноэкранный просмотр фото (portal + крестик сверху справа). */
export function ImageLightboxOverlay({ url, title, onClose, pageUrl }: Props) {
  const src = useProtectedImageSrc(url) ?? url;
  useBodyScrollLock(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="image-lightbox-overlay"
      role="presentation"
      onClick={onClose}
    >
      <button
        type="button"
        className="image-lightbox-close"
        onClick={(e) => {
          e.stopPropagation();
          onClose();
        }}
        aria-label={t("close")}
      >
        <CloseIcon />
      </button>
      <div
        className="image-lightbox"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="image-lightbox-stage">
          <img src={src} alt={title} referrerPolicy="no-referrer" decoding="sync" draggable={false} />
        </div>
        {pageUrl && pageUrl !== url && (
          <a
            className="image-lightbox-source"
            href={pageUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("sourceLink")}
          </a>
        )}
      </div>
    </div>,
    document.body,
  );
}

function CloseIcon() {
  return <X width={20} height={20} strokeWidth={2.2} aria-hidden />;
}
