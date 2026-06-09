import { useEffect, useRef, useState } from "react";
import {
  exportAnswerBlockToDocx,
  exportAnswerBlockToPdf,
  resolveGeneratedDocumentOpenUrl,
} from "../api/client";
import { t } from "../i18n";
import { isLegalDocumentContent } from "../lib/isLegalDocumentContent";
import { useAuthStore } from "../store/authStore";
import { DocumentExportConfirmModal } from "./DocumentExportConfirmModal";
import { ProUpgradeModal } from "./ProUpgradeModal";

type Props = {
  content: string;
  titleHint?: string;
  className?: string;
};

type ExportFormat = "docx" | "pdf";

function sanitizeFilename(title: string): string {
  const base = title
    .replace(/[^\w\s\-а-яА-ЯёЁ]+/gu, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 60);
  return base || "document";
}

function downloadMarkdownFile(content: string, titleHint?: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${sanitizeFilename(titleHint ?? "document")}.md`;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function downloadExportedFile(url: string, filename: string): Promise<void> {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) {
    throw new Error("download failed");
  }
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = filename || "document";
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
}

export function BlockActionsMenu({ content, titleHint, className = "answer-icon-btn" }: Props) {
  const token = useAuthStore((s) => s.token);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = plan === "pro";
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState<ExportFormat | null>(null);
  const [error, setError] = useState(false);
  const [proModalOpen, setProModalOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingFormat, setPendingFormat] = useState<ExportFormat | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const exportingRef = useRef(false);

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
    if (!content.trim() || loading || exportingRef.current) return;
    exportingRef.current = true;
    setLoading(format);
    setError(false);
    try {
      const doc =
        format === "pdf"
          ? await exportAnswerBlockToPdf(token, content, titleHint)
          : await exportAnswerBlockToDocx(token, content, titleHint);
      const url = resolveGeneratedDocumentOpenUrl(doc);
      await downloadExportedFile(url, doc.filename);
    } catch {
      setError(true);
    } finally {
      exportingRef.current = false;
      setLoading(null);
    }
  };

  const runExport = (format: ExportFormat) => {
    if (!isPro) {
      setProModalOpen(true);
      return;
    }
    if (isLegalDocumentContent(content, titleHint)) {
      setPendingFormat(format);
      setConfirmOpen(true);
      return;
    }
    void exportFile(format);
  };

  const handleMenuAction = (action: "docx" | "pdf" | "md") => {
    setOpen(false);
    if (action === "md") {
      if (!isPro) {
        setProModalOpen(true);
        return;
      }
      downloadMarkdownFile(content, titleHint);
      return;
    }
    runExport(action);
  };

  const menuLabel = loading
    ? t("loading")
    : error
      ? t("downloadDocumentFailed")
      : t("downloadDocument");

  return (
    <>
      <div className="block-actions-menu" ref={rootRef}>
        <button
          type="button"
          className={`${className} block-actions-menu-trigger block-actions-download-btn`}
          disabled={loading !== null}
          aria-label={menuLabel}
          title={menuLabel}
          aria-expanded={open}
          aria-haspopup="menu"
          onClick={() => {
            if (!isPro && !open) {
              setProModalOpen(true);
              return;
            }
            setOpen((v) => !v);
          }}
        >
          <span className="block-actions-menu-label">{t("downloadDocument")}</span>
          <span className="block-actions-menu-chevron-wrap" aria-hidden>
            <ChevronIcon open={open} />
          </span>
        </button>
        {open && isPro ? (
          <div className="block-actions-menu-dropdown" role="menu">
            <button
              type="button"
              className="block-actions-menu-item"
              role="menuitem"
              disabled={loading !== null}
              onClick={(e) => {
                e.stopPropagation();
                handleMenuAction("docx");
              }}
            >
              {loading === "docx" ? t("loading") : t("exportBlockDocx")}
            </button>
            <button
              type="button"
              className="block-actions-menu-item"
              role="menuitem"
              disabled={loading !== null}
              onClick={(e) => {
                e.stopPropagation();
                handleMenuAction("pdf");
              }}
            >
              {loading === "pdf" ? t("loading") : t("exportBlockPdf")}
            </button>
            <button
              type="button"
              className="block-actions-menu-item"
              role="menuitem"
              disabled={loading !== null}
              onClick={(e) => {
                e.stopPropagation();
                handleMenuAction("md");
              }}
            >
              {t("exportBlockMd")}
            </button>
          </div>
        ) : null}
      </div>

      <ProUpgradeModal
        open={proModalOpen}
        onClose={() => setProModalOpen(false)}
        title={t("proUpgradeModalTitle")}
        description={t("documentDownloadProOnly")}
      />

      <DocumentExportConfirmModal
        open={confirmOpen}
        onClose={() => {
          setConfirmOpen(false);
          setPendingFormat(null);
        }}
        onConfirm={() => {
          const fmt = pendingFormat;
          setConfirmOpen(false);
          setPendingFormat(null);
          if (fmt) void exportFile(fmt);
        }}
      />
    </>
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
      className={`block-actions-menu-chevron${open ? " block-actions-menu-chevron--open" : ""}`}
    >
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
