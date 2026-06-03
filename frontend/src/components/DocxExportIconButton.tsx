import { useState } from "react";
import { exportAnswerBlockToDocx, resolveGeneratedDocumentOpenUrl } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  content: string;
  titleHint?: string;
  className?: string;
};

export function DocxExportIconButton({
  content,
  titleHint,
  className = "answer-icon-btn",
}: Props) {
  const token = useAuthStore((s) => s.token);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const exportDocx = async () => {
    if (!content.trim() || loading) return;
    setLoading(true);
    setError(false);
    try {
      const doc = await exportAnswerBlockToDocx(token, content, titleHint);
      const url = resolveGeneratedDocumentOpenUrl(doc);
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) setError(true);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  const label = loading
    ? t("loading")
    : error
      ? t("downloadDocumentFailed")
      : t("exportBlockDocx");

  return (
    <button
      type="button"
      className={className}
      disabled={loading}
      onClick={() => void exportDocx()}
      aria-label={label}
      title={label}
    >
      <DocxIcon />
    </button>
  );
}

function DocxIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 3h6l5 5v13a1 1 0 01-1 1H8a1 1 0 01-1-1V4a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <text
        x="12"
        y="16"
        textAnchor="middle"
        fill="currentColor"
        fontSize="5.5"
        fontWeight="700"
        fontFamily="system-ui, sans-serif"
      >
        DOC
      </text>
    </svg>
  );
}
