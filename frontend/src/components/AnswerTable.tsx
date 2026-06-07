import { useMemo, type ReactNode } from "react";
import type { Source } from "../api/client";
import { CopyIconButton } from "./CopyIconButton";
import { SourceChipsRow } from "./SourceChipsRow";
import { formatTableForCopy } from "../lib/formatTableCopy";
import { renderInlineContent } from "../lib/renderInlineContent";
import { parseParagraphCitations } from "../lib/paragraphCitations";

type Props = {
  header: string[];
  rows: string[][];
  sources: Source[];
  keyPrefix: string;
};

function renderCell(text: string, sources: Source[], keyPrefix: string): ReactNode {
  const { indices } = parseParagraphCitations(text);
  const body = renderInlineContent(text, keyPrefix);

  return (
    <>
      {body.length > 0 ? <span className="answer-paragraph-body">{body}</span> : null}
      {indices.length > 0 && (
        <SourceChipsRow
          indices={indices}
          sources={sources}
          className="source-chips-row source-chips-row--block"
        />
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
  const copyText = useMemo(() => formatTableForCopy(header, rows), [header, rows]);

  return (
    <div className="answer-table-wrap">
      <div className="answer-table-header">
        <CopyIconButton text={copyText} />
      </div>
      <div className="answer-table-scroll">
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
    </div>
  );
}
