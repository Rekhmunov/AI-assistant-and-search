import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  title: string;
  contentHtml: string;
  loading?: boolean;
  onClose: () => void;
};

export function LegalDocumentModal({ title, contentHtml, loading = false, onClose }: Props) {
  useBodyScrollLock(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="legal-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="legal-modal app-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="legal-modal-close" onClick={onClose} aria-label={t("close")}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M6 6l12 12M18 6L6 18"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <h2 className="legal-modal-title">{title}</h2>
        {loading ? (
          <p className="muted-text">{t("pageLoading")}</p>
        ) : (
          <div className="legal-modal-body legal-doc-html" dangerouslySetInnerHTML={{ __html: contentHtml }} />
        )}
      </div>
    </div>,
    document.body,
  );
}
