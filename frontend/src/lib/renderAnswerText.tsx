import type { ReactNode } from "react";
import { AnswerTable } from "../components/AnswerTable";
import type { Source } from "../api/client";
import { formatMarkdownText } from "./formatMarkdownText";
import { splitTextWithMarkdownTables } from "./parseMarkdownTables";
import { renderTextWithCitations } from "./parseCitations";

function renderPlainTextFragment(text: string, sources: Source[], keyPrefix: string): ReactNode[] {
  const formatted = formatMarkdownText(text);
  if (!formatted) return [];

  const nodes: ReactNode[] = [];
  const inlineRe = /`([^`\n]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let k = 0;

  const pushPlain = (chunk: string) => {
    if (!chunk) return;
    const cited = renderTextWithCitations(chunk, sources);
    cited.forEach((node, i) => {
      if (typeof node === "string") {
        nodes.push(<span key={`${keyPrefix}-p-${k++}-${i}`}>{node}</span>);
      } else {
        nodes.push(node);
      }
    });
  };

  while ((match = inlineRe.exec(formatted)) !== null) {
    if (match.index > last) {
      pushPlain(formatted.slice(last, match.index));
    }
    nodes.push(
      <code key={`${keyPrefix}-ic-${k++}`} className="answer-inline-code">
        {match[1]}
      </code>,
    );
    last = match.index + match[0].length;
  }

  if (last < formatted.length) {
    pushPlain(formatted.slice(last));
  }

  if (nodes.length === 0 && formatted) {
    pushPlain(formatted);
  }

  return nodes;
}

/** Текстовый фрагмент: таблицы GFM + markdown без блоков + [1] + inline `code`. */
export function renderAnswerTextSegment(text: string, sources: Source[], keyPrefix: string): ReactNode[] {
  const blocks = splitTextWithMarkdownTables(text);
  const nodes: ReactNode[] = [];
  let bi = 0;

  for (const block of blocks) {
    const id = bi++;
    if (block.type === "table") {
      nodes.push(
        <AnswerTable
          key={`${keyPrefix}-tbl-${id}`}
          header={block.header}
          rows={block.rows}
          sources={sources}
          keyPrefix={`${keyPrefix}-tbl-${id}`}
        />,
      );
      continue;
    }
    const chunk = renderPlainTextFragment(block.content, sources, `${keyPrefix}-t-${id}`);
    if (chunk.length > 0) {
      nodes.push(
        <span key={`${keyPrefix}-txt-${id}`} className="answer-text-part">
          {chunk}
        </span>,
      );
    }
  }

  return nodes;
}
