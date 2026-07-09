import type { ReactNode } from "react";
import { AnswerTable } from "../components/AnswerTable";
import { SourceChipsRow } from "../components/SourceChipsRow";
import type { Source } from "../api/client";
import { parseAnswerMarkdownBlocks } from "./parseAnswerMarkdownBlocks";
import { mergeCitationIndices, parseParagraphCitations } from "./paragraphCitations";
import { splitTextWithMarkdownTables } from "./parseMarkdownTables";
import { renderInlineContent } from "./renderInlineContent";

const BLOCK_CHIPS_CLASS = "source-chips-row source-chips-row--block";

function renderInlineText(text: string, keyPrefix: string): ReactNode[] {
  return renderInlineContent(text, keyPrefix);
}

function renderBlockSources(indices: number[], sources: Source[]): ReactNode {
  if (!indices.length) return null;
  return (
    <SourceChipsRow
      indices={indices}
      sources={sources}
      className={BLOCK_CHIPS_CLASS}
    />
  );
}

function renderTextParagraph(paragraph: string, sources: Source[], keyPrefix: string): ReactNode {
  const { text, indices } = parseParagraphCitations(paragraph);
  const body = renderInlineText(text, keyPrefix);

  if (!body.length && indices.length === 0) {
    return null;
  }

  return (
    <p className="answer-paragraph">
      <span className="answer-paragraph-body">{body}</span>
      {renderBlockSources(indices, sources)}
    </p>
  );
}

function renderListItemBody(item: string, keyPrefix: string): ReactNode | null {
  const { text } = parseParagraphCitations(item);
  const body = renderInlineText(text, keyPrefix);
  if (!body.length) return null;
  return <span className="answer-list-item-body">{body}</span>;
}

function renderMarkdownBlock(
  block: ReturnType<typeof parseAnswerMarkdownBlocks>[number],
  sources: Source[],
  keyPrefix: string,
): ReactNode | null {
  if (block.type === "heading") {
    const { text, indices } = parseParagraphCitations(block.text);
    const body = renderInlineText(text, `${keyPrefix}-h`);
    if (!body.length && indices.length === 0) return null;
    const level = block.level ?? 2;
    const Tag = level <= 2 ? "h2" : level === 3 ? "h3" : "h4" as keyof JSX.IntrinsicElements;
    const cls = `answer-heading answer-heading--h${level}`;
    return (
      <Tag className={cls}>
        <span className="answer-heading-body">{body}</span>
        {renderBlockSources(indices, sources)}
      </Tag>
    );
  }

  if (block.type === "blockquote") {
    return (
      <blockquote className="answer-blockquote">
        {block.lines.map((line, i) => {
          const { text, indices } = parseParagraphCitations(line);
          const body = renderInlineText(text, `${keyPrefix}-bq-${i}`);
          if (!body.length) return null;
          return (
            <p key={i} className="answer-blockquote-line">
              <span>{body}</span>
              {renderBlockSources(indices, sources)}
            </p>
          );
        })}
      </blockquote>
    );
  }

  if (block.type === "ul" || block.type === "ol") {
    const Tag = block.type === "ol" ? "ol" : "ul";
    const itemIndices: number[][] = [];
    const items = block.items
      .map((item, index) => {
        const parsed = parseParagraphCitations(item);
        itemIndices.push(parsed.indices);
        const body = renderListItemBody(item, `${keyPrefix}-li-${index}`);
        if (!body) return null;
        return (
          <li key={`${keyPrefix}-li-${index}`} className="answer-list-item">
            {body}
          </li>
        );
      })
      .filter(Boolean);
    if (!items.length) return null;

    const indices = mergeCitationIndices(...itemIndices);
    return (
      <div className="answer-list-block">
        <Tag className={`answer-list answer-list--${block.type}`}>{items}</Tag>
        {renderBlockSources(indices, sources)}
      </div>
    );
  }

  return renderTextParagraph(block.text, sources, keyPrefix);
}

function renderPlainTextFragment(text: string, sources: Source[], keyPrefix: string): ReactNode | null {
  const blocks = parseAnswerMarkdownBlocks(text);
  if (!blocks.length) return null;

  return (
    <div className="answer-text-part">
      {blocks.map((block, index) => {
        const node = renderMarkdownBlock(block, sources, `${keyPrefix}-b-${index}`);
        if (!node) return null;
        return <div key={`${keyPrefix}-block-${index}`}>{node}</div>;
      })}
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
