import type { ReactNode } from "react";
import type { Source } from "../api/client";
import { SourceChipsRow } from "./SourceChipsRow";
import { formatMarkdownText } from "../lib/formatMarkdownText";
import { parseParagraphCitations } from "../lib/paragraphCitations";

type Props = {
  header: string[];
  rows: string[][];
  sources: Source[];
  keyPrefix: string;
};

function renderCell(text: string, sources: Source[], keyPrefix: string): ReactNode {
  const plain = formatMarkdownText(text);
  const { text: clean, indices } = parseParagraphCitations(plain);
  const body = clean.replace(/\[\d+\]/g, "");

  return (
    <>
      {body}
      {indices.length > 0 && (
        <SourceChipsRow indices={indices} sources={sources} className="source-chips-row" />
      )}
    </>
  );
}

export function AnswerTable({ header, rows, sources, keyPrefix }: Props) {
  const colCount = Math.max(header.length, ...rows.map((r) => r.length), 1);

  const padRow = (cells: string[]) => {
    const out = [...cells];
    while (out.length < colCount) out.push("");
    return out.slice(0, colCount);
  };

  const head = padRow(header);
  const body = rows.map(padRow);

  return (
    <div className="answer-table-wrap">
      <table className="answer-table">
        <thead>
          <tr>
            {head.map((cell, i) => (
              <th key={`${keyPrefix}-h-${i}`}>{renderCell(cell, sources, `${keyPrefix}-h-${i}`)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={`${keyPrefix}-r-${ri}`}>
              {row.map((cell, ci) => (
                <td key={`${keyPrefix}-r-${ri}-c-${ci}`}>
                  {renderCell(cell, sources, `${keyPrefix}-r-${ri}-c-${ci}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
