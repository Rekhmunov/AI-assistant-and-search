import { formatMarkdownText } from "./formatMarkdownText";
import { parseParagraphCitations } from "./paragraphCitations";

function plainTableCell(raw: string): string {
  const { text } = parseParagraphCitations(raw);
  return formatMarkdownText(text).replace(/\s+/g, " ").trim();
}

function escapeMarkdownCell(cell: string): string {
  return cell.replace(/\|/g, "\\|");
}

/** Markdown-таблица для буфера обмена (заголовки + строки). */
export function formatTableForCopy(header: string[], rows: string[][]): string {
  const colCount = Math.max(header.length, ...rows.map((r) => r.length), 1);
  const pad = (cells: string[]) => {
    const out = cells.map(plainTableCell);
    while (out.length < colCount) out.push("");
    return out.slice(0, colCount).map(escapeMarkdownCell);
  };

  const head = pad(header);
  const body = rows.map(pad);
  const sep = head.map(() => "---");

  const line = (cells: string[]) => `| ${cells.join(" | ")} |`;
  return [line(head), line(sep), ...body.map(line)].join("\n");
}
