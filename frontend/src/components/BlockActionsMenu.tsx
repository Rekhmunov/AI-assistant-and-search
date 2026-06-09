import { useEffect, useRef, useState } from "react";
import {
  exportAnswerBlockToDocx,
  exportAnswerBlockToPdf,
  resolveGeneratedDocumentOpenUrl,
} from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  content: string;
  titleHint?: string;
  className?: string;
};

type ExportFormat = "docx" | "pdf";

export function BlockActionsMenu({ content, titleHint, className = "answer-icon-btn" }: Props) {
  const token = useAuthStore((s) => s.token);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<ExportFormat | null>(null);
  const [error, setError] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const el = rootRef.current;
      if (!el || (e.target instanceof Node && el.contains(e.target))) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown, { passive: true });
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const exportFile = async (format: ExportFormat) => {
    if (!content.trim() || loading) return;
    setLoading(format);
    setError(false);
    try {
      const doc =
        format === "pdf"
          ? await exportAnswerBlockToPdf(token, content, titleHint)
          : await exportAnswerBlockToDocx(token, content, titleHint);
      const url = resolveGeneratedDocumentOpenUrl(doc);
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) setError(true);
    } catch {
      setError(true);
    } finally {
      setLoading(null);
    }
  };

  const menuLabel = loading
    ? t("loading")
    : error
      ? t("downloadDocumentFailed")
      : t("downloadDocument");

  return (
    <div className="block-actions-menu" ref={rootRef}>
      <button
        type="button"
        className={`${className} block-actions-menu-trigger block-actions-download-btn`}
        disabled={loading !== null}
        aria-label={menuLabel}
        title={menuLabel}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="block-actions-menu-label">{t("downloadDocument")}</span>
        <ChevronIcon open={open} />
      </button>
      {open ? (
        <div className="block-actions-menu-dropdown" role="menu">
          <button
            type="button"
            className="block-actions-menu-item"
            role="menuitem"
            disabled={loading !== null}
            onClick={() => {
              setOpen(false);
              void exportFile("docx");
            }}
          >
            {loading === "docx" ? t("loading") : t("exportBlockDocx")}
          </button>
          <button
            type="button"
            className="block-actions-menu-item"
            role="menuitem"
            disabled={loading !== null}
            onClick={() => {
              setOpen(false);
              void exportFile("pdf");
            }}
          >
            {loading === "pdf" ? t("loading") : t("exportBlockPdf")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={open ? "block-actions-menu-chevron--open" : undefined}
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
