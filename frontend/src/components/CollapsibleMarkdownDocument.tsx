import { useMemo, useState } from "react";
import { t } from "../i18n";
import { CopyIconButton } from "./CopyIconButton";
import { DocxExportIconButton } from "./DocxExportIconButton";

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
  return (
    <div className="markdown-document-block">
      <div className="markdown-document-header">
        <span className="markdown-document-title" title={title}>
          {title}
        </span>
        <div className="markdown-document-actions">
          <CopyIconButton text={content} />
          <DocxExportIconButton content={content} titleHint={title} />
        </div>
      </div>
      <div
        className={`markdown-document-body${shouldCollapse && !expanded ? " markdown-document-body--collapsed" : ""}`}
        style={
          shouldCollapse && !expanded
            ? { maxHeight: `${COLLAPSED_MAX_VH}vh` }
            : undefined
        }
      >
        <pre className="markdown-document-pre">{content}</pre>
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
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d={direction === "up" ? "M6 14l6-6 6 6" : "M6 10l6 6 6-6"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
