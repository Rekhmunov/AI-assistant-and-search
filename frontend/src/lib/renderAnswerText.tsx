import type { ReactNode } from "react";
import { AnswerTable } from "../components/AnswerTable";
import { SourceChipsRow } from "../components/SourceChipsRow";
import type { Source } from "../api/client";
import { formatMarkdownText } from "./formatMarkdownText";
import { parseParagraphCitations } from "./paragraphCitations";
import { splitTextWithMarkdownTables } from "./parseMarkdownTables";

function renderInlineText(text: string, keyPrefix: string): ReactNode[] {
  const formatted = formatMarkdownText(text);
  if (!formatted) return [];

  const nodes: ReactNode[] = [];
  const inlineRe = /`([^`\n]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let k = 0;

  const pushPlain = (chunk: string) => {
    if (!chunk) return;
    nodes.push(
      <span key={`${keyPrefix}-p-${k++}`}>{chunk.replace(/\[\d+\]/g, "")}</span>,
    );
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

function renderTextParagraph(paragraph: string, sources: Source[], keyPrefix: string): ReactNode {
  const { text, indices } = parseParagraphCitations(paragraph);
  const body = renderInlineText(text, keyPrefix);

  if (!body.length && indices.length === 0) {
    return null;
  }

  return (
    <div className="answer-paragraph">
      {body.length > 0 && <div className="answer-paragraph-body">{body}</div>}
      {indices.length > 0 && <SourceChipsRow indices={indices} sources={sources} />}
    </div>
  );
}

function renderPlainTextFragment(text: string, sources: Source[], keyPrefix: string): ReactNode | null {
  const formatted = formatMarkdownText(text);
  if (!formatted) return null;

  const paragraphs = formatted.split(/\n\n+/).filter((p) => p.trim());
  if (!paragraphs.length) return null;

  return (
    <div className="answer-text-part">
      {paragraphs.map((paragraph, index) => (
        <div key={`${keyPrefix}-para-${index}`}>
          {renderTextParagraph(paragraph, sources, `${keyPrefix}-p-${index}`)}
        </div>
      ))}
    </div>
  );
}

/** Текстовый фрагмент: таблицы GFM + markdown без блоков + чипы источников + inline `code`. */
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
    if (chunk) nodes.push(<div key={`${keyPrefix}-txt-${id}`}>{chunk}</div>);
  }

  return nodes;
}
