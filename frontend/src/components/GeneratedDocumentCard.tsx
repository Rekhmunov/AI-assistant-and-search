import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent, resolveGeneratedDocumentOpenUrl } from "../api/client";
import { FileText } from "lucide-react";
import { t } from "../i18n";
import { downloadRemoteFile } from "../lib/triggerBrowserDownload";

type Props = {
  document: GeneratedDocumentInfo;
};

export function GeneratedDocumentCard({ document: doc }: Props) {
  const openUrl = resolveGeneratedDocumentOpenUrl(doc);
  const filename = doc.filename || "document.docx";

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
          onClick={() => void downloadRemoteFile(openUrl, filename)}
        >
          {t("downloadDocument")}
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
