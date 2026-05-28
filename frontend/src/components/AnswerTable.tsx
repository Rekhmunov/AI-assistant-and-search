import type { ReactNode } from "react";
import type { Source } from "../api/client";
import { formatMarkdownText } from "../lib/formatMarkdownText";
import { renderTextWithCitations } from "../lib/parseCitations";

type Props = {
  header: string[];
  rows: string[][];
  sources: Source[];
  keyPrefix: string;
};

function renderCell(text: string, sources: Source[]): ReactNode {
  const plain = formatMarkdownText(text);
  const cited = renderTextWithCitations(plain, sources);
  if (cited.length === 1 && typeof cited[0] === "string") {
    return cited[0];
  }
  return <>{cited}</>;
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
              <th key={`${keyPrefix}-h-${i}`}>{renderCell(cell, sources)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={`${keyPrefix}-r-${ri}`}>
              {row.map((cell, ci) => (
                <td key={`${keyPrefix}-r-${ri}-c-${ci}`}>
                  {renderCell(cell, sources)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
