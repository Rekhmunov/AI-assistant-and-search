import { useState } from "react";
import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import { isProPlan } from "../lib/copyAttribution";

type Props = {
  document: GeneratedDocumentInfo;
};

export function GeneratedDocumentCard({ document: doc }: Props) {
  const token = useAuthStore((s) => s.token);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const download = async () => {
    setDownloading(true);
    setError("");
    try {
      const blob = await fetchFileContent(token, doc.id, {
        shareUrl: doc.share_url,
        downloadUrl: doc.url,
      });
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement("a");
      a.href = url;
      a.download = doc.filename || "document.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("downloadDocumentFailed"));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="generated-document-card">
      <div className="generated-document-card-icon" aria-hidden>
        <DocxIcon />
      </div>
      <div className="generated-document-card-body">
        <span className="generated-document-card-name" title={doc.filename}>
          {doc.filename}
        </span>
        <button
          type="button"
          className="btn btn-secondary generated-document-card-download"
          disabled={downloading}
          onClick={() => void download()}
        >
          {downloading ? t("loading") : t("downloadDocument")}
        </button>
        {error ? <p className="generated-document-card-error">{error}</p> : null}
      </div>
    </div>
  );
}

export async function shareGeneratedDocument(
  doc: GeneratedDocumentInfo,
  token: string | null,
  isPro: boolean,
): Promise<boolean> {
  const shareText = isPro ? undefined : t("shareDocumentGlosix");
  try {
    const blob = await fetchFileContent(token, doc.id, { shareUrl: doc.share_url });
    const file = new File([blob], doc.filename || "document.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    if (navigator.share && navigator.canShare?.({ files: [file] })) {
      await navigator.share({
        files: [file],
        text: shareText,
        title: doc.filename,
      });
      return true;
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return true;
  }

  const API_BASE = import.meta.env.VITE_API_URL || "";
  const link = doc.share_url
    ? doc.share_url.startsWith("http")
      ? doc.share_url
      : `${API_BASE}${doc.share_url}`
    : doc.url?.startsWith("http")
      ? doc.url
      : `${API_BASE}/api/files/${doc.id}/content`;

  const clipboardText = shareText ? `${shareText}\n${link}` : link;
  try {
    await navigator.clipboard.writeText(clipboardText);
    return true;
  } catch {
    return false;
  }
}

function DocxIcon() {
  return (
    <svg className="generated-document-card-icon-svg" width="28" height="28" viewBox="0 0 32 32" fill="none">
      <rect x="5" y="3" width="22" height="26" rx="4" fill="currentColor" opacity="0.12" />
      <path
        d="M11 4h7l7 7v17a2 2 0 01-2 2H11a2 2 0 01-2-2V6a2 2 0 012-2z"
        fill="#fff"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M18 4v7h7" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <rect x="10" y="14" width="12" height="1.5" rx="0.75" fill="currentColor" opacity="0.35" />
      <rect x="10" y="18" width="9" height="1.5" rx="0.75" fill="currentColor" opacity="0.35" />
      <rect x="10" y="22" width="10" height="1.5" rx="0.75" fill="currentColor" opacity="0.35" />
      <text
        x="16"
        y="12.5"
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
