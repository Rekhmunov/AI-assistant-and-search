import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";
import { t } from "../i18n";
import { truncateDocTitle } from "../lib/truncateDocTitle";
import { BlockActionsMenu } from "./BlockActionsMenu";
import { MarkdownDocumentPreview } from "./MarkdownDocumentPreview";

// Документы длиннее порога сворачиваются — показывают preview + кнопку «Развернуть»
const COLLAPSE_CHAR_THRESHOLD = 2000;
// Сколько символов показывать в свёрнутом виде (обрезаем по границе абзаца)
const PREVIEW_CHARS = 800;

type Props = {
  title: string;
  content: string;
  collapsible?: boolean;
};

function getPreviewContent(content: string): string {
  if (content.length <= PREVIEW_CHARS) return content;
  // Обрезаем по ближайшей границе абзаца (пустая строка)
  const sub = content.slice(0, PREVIEW_CHARS);
  const lastPara = sub.lastIndexOf("\n\n");
  return (lastPara > 200 ? sub.slice(0, lastPara) : sub) + "\n\n…";
}

export function CollapsibleMarkdownDocument({ title, content, collapsible }: Props) {
  const shouldCollapse = useMemo(
    () => collapsible ?? content.length > COLLAPSE_CHAR_THRESHOLD,
    [collapsible, content.length],
  );
  const [expanded, setExpanded] = useState(!shouldCollapse);
  const displayTitle = useMemo(() => truncateDocTitle(title), [title]);
  const previewContent = useMemo(() => getPreviewContent(content), [content]);

  return (
    <div className="markdown-document-block">
      <div className="markdown-document-header">
        <span className="markdown-document-type-label">Документ</span>
        <span className="markdown-document-title" title={title}>
          {displayTitle}
        </span>
        <BlockActionsMenu
          content={content}
          titleHint={title}
          className="markdown-document-actions block-actions-menu-btn"
        />
      </div>
      <div className="markdown-document-body">
        <MarkdownDocumentPreview content={expanded ? content : previewContent} />
      </div>
      {shouldCollapse ? (
        <button
          type="button"
          className="markdown-document-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <span>{expanded ? t("markdownDocumentCollapse") : t("markdownDocumentExpand")}</span>
          <ChevronIcon direction={expanded ? "up" : "down"} />
        </button>
      ) : null}
    </div>
  );
}

function ChevronIcon({ direction }: { direction: "up" | "down" }) {
  if (direction === "up") {
    return <ChevronUp width={16} height={16} strokeWidth={2} aria-hidden />;
  }
  return <ChevronDown width={16} height={16} strokeWidth={2} aria-hidden />;
}
