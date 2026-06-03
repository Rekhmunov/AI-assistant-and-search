import { useState } from "react";
import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import { isProPlan } from "../lib/copyAttribution";

const API_BASE = import.meta.env.VITE_API_URL || "";

type Props = {
  document: GeneratedDocumentInfo;
};

export function GeneratedDocumentCard({ document: doc }: Props) {
  const token = useAuthStore((s) => s.token);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);
  const [downloading, setDownloading] = useState(false);

  const downloadHref = doc.url
    ? doc.url.startsWith("http")
      ? doc.url
      : `${API_BASE}${doc.url}`
    : `${API_BASE}/api/files/${doc.id}/content`;

  const shareHref = doc.share_url
    ? doc.share_url.startsWith("http")
      ? doc.share_url
      : `${API_BASE}${doc.share_url}`
    : downloadHref;

  const download = async () => {
    setDownloading(true);
    try {
      const blob = await fetchFileContent(token, doc.id);
      const url = URL.createObjectURL(blob);
      const a = window.document.createElement("a");
      a.href = url;
      a.download = doc.filename || "document.docx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      window.open(downloadHref, "_blank", "noopener,noreferrer");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="generated-document-card">
      <div className="generated-document-card-icon" aria-hidden>
        <DocIcon />
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
    const blob = await fetchFileContent(token, doc.id);
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

function DocIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14 2H8a2 2 0 00-2 2v16a2 2 0 002 2h8a2 2 0 002-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
