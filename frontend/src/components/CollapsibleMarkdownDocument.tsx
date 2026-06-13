import { useMemo, useState } from "react";
import { ChevronUp, ChevronDown } from "lucide-react";
import { t } from "../i18n";
import { truncateDocTitle } from "../lib/truncateDocTitle";
import { BlockToolbarActions } from "./BlockToolbarActions";
import { MarkdownDocumentPreview } from "./MarkdownDocumentPreview";

const COLLAPSE_CHAR_THRESHOLD = 1200;
const COLLAPSED_MAX_VH = 50;

type Props = {
  title: string;
  content: string;
  collapsible?: boolean;
};

export function CollapsibleMarkdownDocument({ title, content, collapsible }: Props) {
  const shouldCollapse = useMemo(
    () => collapsible ?? content.length > COLLAPSE_CHAR_THRESHOLD,
    [collapsible, content.length],
  );
  const [expanded, setExpanded] = useState(!shouldCollapse);
  const displayTitle = useMemo(() => truncateDocTitle(title), [title]);

  return (
    <div className="markdown-document-block">
      <div className="markdown-document-header">
        <span className="markdown-document-title" title={title}>
          {displayTitle}
        </span>
        <BlockToolbarActions
          className="markdown-document-actions"
          copyText={content}
          docx={{ content, titleHint: title }}
        />
      </div>
      <div
        className={`markdown-document-body${shouldCollapse && !expanded ? " markdown-document-body--collapsed" : ""}`}
        style={
          shouldCollapse && !expanded
            ? { maxHeight: `${COLLAPSED_MAX_VH}vh` }
            : undefined
        }
      >
        <MarkdownDocumentPreview content={content} />
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
