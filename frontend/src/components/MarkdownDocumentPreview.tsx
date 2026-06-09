import type { ReactNode } from "react";
import { parseAnswerMarkdownBlocks } from "../lib/parseAnswerMarkdownBlocks";
import { splitTextWithMarkdownTables } from "../lib/parseMarkdownTables";
import { renderInlineContent } from "../lib/renderInlineContent";

type Props = {
  content: string;
};

function renderParagraph(text: string, key: string): ReactNode {
  const blocks = splitTextWithMarkdownTables(text);
  return blocks.map((block, i) => {
    if (block.type === "table") {
      return (
        <div key={`${key}-tbl-${i}`} className="markdown-document-table-wrap">
          <table className="markdown-document-table">
            <thead>
              <tr>
                {block.header.map((cell, ci) => (
                  <th key={ci}>{cell}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <p key={`${key}-p-${i}`} className="markdown-document-paragraph">
        {renderInlineContent(block.content, `${key}-p-${i}`)}
      </p>
    );
  });
}

export function MarkdownDocumentPreview({ content }: Props) {
  const blocks = parseAnswerMarkdownBlocks(content);
  if (!blocks.length) {
    return (
      <div className="markdown-document-rendered">
        {renderParagraph(content, "fallback")}
      </div>
    );
  }

  return (
    <div className="markdown-document-rendered">
      {blocks.map((block, i) => {
        const key = `md-${i}`;
        if (block.type === "heading") {
          return (
            <h3 key={key} className="markdown-document-heading">
              {renderInlineContent(block.text, key)}
            </h3>
          );
        }
        if (block.type === "ul") {
          return (
            <ul key={key} className="markdown-document-list">
              {block.items.map((item, ii) => (
                <li key={`${key}-${ii}`}>{renderInlineContent(item, `${key}-${ii}`)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === "ol") {
          return (
            <ol key={key} className="markdown-document-list markdown-document-list--ol">
              {block.items.map((item, ii) => (
                <li key={`${key}-${ii}`}>{renderInlineContent(item, `${key}-${ii}`)}</li>
              ))}
            </ol>
          );
        }
        return (
          <div key={key} className="markdown-document-paragraph-group">
            {renderParagraph(block.text, key)}
          </div>
        );
      })}
    </div>
  );
}
