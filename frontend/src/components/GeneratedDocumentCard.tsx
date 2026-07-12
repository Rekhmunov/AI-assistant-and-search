import { useState } from "react";
import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent, resolveGeneratedDocumentOpenUrl } from "../api/client";
import { FileText, Archive } from "lucide-react";
import { t } from "../i18n";
import { downloadRemoteFile } from "../lib/triggerBrowserDownload";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "";

type Props = {
  document: GeneratedDocumentInfo;
  extraDocuments?: GeneratedDocumentInfo[];
};

function isExpired(doc: GeneratedDocumentInfo): boolean {
  if (!doc.expires_at) return false;
  return new Date(doc.expires_at) < new Date();
}

function SingleDocumentRow({ doc }: { doc: GeneratedDocumentInfo }) {
  const openUrl = resolveGeneratedDocumentOpenUrl(doc);
  const filename = doc.filename || "document";
  const expired = isExpired(doc);
  return (
    <div className={`generated-document-card${expired ? " generated-document-card--expired" : ""}`}>
      <div className="generated-document-card-icon" aria-hidden>
        <DocxIcon />
      </div>
      <div className="generated-document-card-body">
        <span className="generated-document-card-name" title={doc.filename}>
          {doc.filename}
        </span>
        {expired ? (
          <span className="generated-document-card-expired-label">
            Файл удалён (срок хранения истёк)
          </span>
        ) : (
          <div className="generated-document-card-actions">
            <button
              type="button"
              className="btn btn-secondary generated-document-card-download"
              onClick={() => void downloadRemoteFile(openUrl, filename)}
            >
              {t("downloadDocument")}
            </button>
            {openUrl && (
              <a
                href={openUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary generated-document-card-open"
              >
                Открыть
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function GeneratedDocumentCard({ document: doc, extraDocuments }: Props) {
  const allDocs = [doc, ...(extraDocuments ?? [])];
  const token = useAuthStore((s) => s.token);
  const [zipping, setZipping] = useState(false);
  const [zipError, setZipError] = useState("");

  if (allDocs.length === 1) {
    return <SingleDocumentRow doc={doc} />;
  }

  // Multiple files → single ZIP download
  const handleDownloadZip = async () => {
    setZipping(true);
    setZipError("");
    try {
      const fileIds = allDocs.map((d) => d.id).filter(Boolean);
      // Derive a common zip name from the first file (strip _compressed/_pages suffix)
      const baseName = (allDocs[0].filename || "archive")
        .replace(/_compressed\.pdf$/i, "")
        .replace(/_pages\.zip$/i, "")
        .replace(/\.[^.]+$/, "");
      const res = await fetch(`${API_BASE}/api/files/zip`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ file_ids: fileIds, zip_name: baseName }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Ошибка ${res.status}`);
      }
      const data = await res.json();
      await downloadRemoteFile(data.download_url, data.filename);
    } catch (e: unknown) {
      setZipError(e instanceof Error ? e.message : "Ошибка создания архива");
    } finally {
      setZipping(false);
    }
  };

  const totalFiles = allDocs.length;

  return (
    <div className="generated-document-card generated-document-card--multi">
      <div className="generated-document-card-icon" aria-hidden>
        <ArchiveIcon />
      </div>
      <div className="generated-document-card-body">
        <span className="generated-document-card-name">
          {totalFiles} файла готовы
        </span>
        <span className="generated-document-card-files-list">
          {allDocs.map((d, i) => (
            <span key={d.id ?? i} className="generated-document-card-file-item">
              📄 {d.filename}
            </span>
          ))}
        </span>
        {zipError && (
          <span className="generated-document-card-error">⚠️ {zipError}</span>
        )}
        <button
          type="button"
          className="btn btn-secondary generated-document-card-download"
          onClick={() => void handleDownloadZip()}
          disabled={zipping}
        >
          {zipping ? "Создаём архив…" : `⬇️ Скачать все (ZIP)`}
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
    const blob = await fetchFileContent(token, doc.id, {
      shareUrl: doc.share_url,
      downloadUrl: doc.url,
    });
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

  const link = resolveGeneratedDocumentOpenUrl(doc);
  const clipboardText = shareText ? `${shareText}\n${link}` : link;
  try {
    await navigator.clipboard.writeText(clipboardText);
    return true;
  } catch {
    return false;
  }
}

function DocxIcon() {
  return <FileText className="generated-document-card-icon-svg" width={28} height={28} strokeWidth={1.5} />;
}

function ArchiveIcon() {
  return <Archive className="generated-document-card-icon-svg" width={28} height={28} strokeWidth={1.5} />;
}
