import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent, resolveGeneratedDocumentOpenUrl } from "../api/client";
import { FileText } from "lucide-react";
import { t } from "../i18n";
import { downloadRemoteFile } from "../lib/triggerBrowserDownload";

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
          <button
            type="button"
            className="btn btn-secondary generated-document-card-download"
            onClick={() => void downloadRemoteFile(openUrl, filename)}
          >
            {t("downloadDocument")}
          </button>
        )}
      </div>
    </div>
  );
}

export function GeneratedDocumentCard({ document: doc, extraDocuments }: Props) {
  const allDocs = [doc, ...(extraDocuments ?? [])];

  if (allDocs.length === 1) {
    return <SingleDocumentRow doc={doc} />;
  }

  return (
    <div className="generated-document-cards-multi">
      {allDocs.map((d, i) => (
        <SingleDocumentRow key={d.id ?? i} doc={d} />
      ))}
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
