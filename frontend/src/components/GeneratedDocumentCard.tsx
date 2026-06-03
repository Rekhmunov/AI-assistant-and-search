import type { GeneratedDocumentInfo } from "../api/client";
import { fetchFileContent, resolveGeneratedDocumentOpenUrl } from "../api/client";
import { t } from "../i18n";

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
        <a
          href={openUrl}
          target="_blank"
          rel="noopener noreferrer"
          download={filename}
          className="btn btn-secondary generated-document-card-download"
        >
          {t("downloadDocument")}
        </a>
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
