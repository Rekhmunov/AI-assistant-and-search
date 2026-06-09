import { useMemo, useState } from "react";
import { t } from "../i18n";
import { formatChartSpecForCopy, parseChartSpec } from "../lib/parseChartSpec";
import { truncateDocTitle } from "../lib/truncateDocTitle";
import { AnswerChart } from "./AnswerChart";
import { BlockToolbarActions } from "./BlockToolbarActions";
import { MarkdownDocumentPreview } from "./MarkdownDocumentPreview";

const COLLAPSE_CHAR_THRESHOLD = 1200;
const COLLAPSED_MAX_VH = 50;

type Props = {
  markdownParts: string[];
  charts: string[];
  partial?: boolean;
};

function resolveTitle(markdownParts: string[]): string {
  for (const part of markdownParts) {
    const title =
      part
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("#"))?.replace(/^#+\s*/, "") ||
      part
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.length >= 8);
    if (title) return title;
  }
  return "Документ";
}

function buildCopyText(markdownParts: string[], charts: string[]): string {
  const chunks: string[] = [];
  const maxLen = Math.max(markdownParts.length, charts.length + 1);
  for (let i = 0; i < maxLen; i += 1) {
    const md = markdownParts[i]?.trim();
    if (md) chunks.push(md);
    const chartRaw = charts[i]?.trim();
    if (chartRaw) {
      const spec = parseChartSpec(chartRaw);
      chunks.push(spec ? formatChartSpecForCopy(spec) : chartRaw);
    }
  }
  return chunks.join("\n\n");
}

export function DocumentAnswerBlock({ markdownParts, charts, partial }: Props) {
  const title = useMemo(() => resolveTitle(markdownParts), [markdownParts]);
  const displayTitle = useMemo(() => truncateDocTitle(title), [title]);
  const copyText = useMemo(() => buildCopyText(markdownParts, charts), [markdownParts, charts]);
  const combinedMarkdown = useMemo(() => markdownParts.join("\n\n"), [markdownParts]);

  const contentLen = combinedMarkdown.length + charts.join("").length;
  const shouldCollapse = contentLen > COLLAPSE_CHAR_THRESHOLD;
  const [expanded, setExpanded] = useState(!shouldCollapse);

  const chartSpecs = useMemo(
    () => charts.map((raw) => ({ raw, spec: partial ? null : parseChartSpec(raw) })),
    [charts, partial],
  );

  const maxSlots = Math.max(markdownParts.length, charts.length + 1);

  return (
    <div className="markdown-document-block">
      <div className="markdown-document-header">
        <span className="markdown-document-title" title={title}>
          {displayTitle}
        </span>
        <BlockToolbarActions
          className="markdown-document-actions"
          copyText={copyText}
          docx={{ content: combinedMarkdown, titleHint: title }}
        />
      </div>
      <div
        className={`markdown-document-body${shouldCollapse && !expanded ? " markdown-document-body--collapsed" : ""}`}
        style={
          shouldCollapse && !expanded ? { maxHeight: `${COLLAPSED_MAX_VH}vh` } : undefined
        }
      >
        {Array.from({ length: maxSlots }, (_, slot) => {
          const md = markdownParts[slot];
          const chart = chartSpecs[slot];
          return (
            <div key={`doc-slot-${slot}`} className="document-answer-slot">
              {md ? <MarkdownDocumentPreview content={md} /> : null}
              {chart ? (
                chart.spec ? (
                  <div className="document-answer-chart">
                    <AnswerChart spec={chart.spec} />
                  </div>
                ) : (
                  <div className="document-answer-chart-fallback muted-text">
                    {partial ? t("answerPreparing") : t("chartParseFailed")}
                  </div>
                )
              ) : null}
            </div>
          );
        })}
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
