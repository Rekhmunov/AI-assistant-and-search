/** Блоки текста и markdown-таблицы (GFM: строки с |). */

export type TextTableBlock =
  | { type: "text"; content: string }
  | { type: "table"; header: string[]; rows: string[][] };

function isTableLine(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.endsWith("|") && t.length > 2;
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

function isSeparatorCells(cells: string[]): boolean {
  if (cells.length === 0) return false;
  return cells.every((c) => /^:?-{2,}:?$/.test(c.replace(/\s/g, "")));
}

function parseTableLines(lines: string[]): { header: string[]; rows: string[][] } | null {
  if (lines.length === 0) return null;
  const parsed = lines.map(splitTableRow);
  if (parsed.some((row) => row.length < 2)) return null;

  if (lines.length >= 2 && isSeparatorCells(parsed[1])) {
    return { header: parsed[0], rows: parsed.slice(2) };
  }
  return { header: parsed[0], rows: parsed.slice(1) };
}

/**
 * Делит текст на фрагменты; подряд идущие строки `| a | b |` — таблица.
 */
export function splitTextWithMarkdownTables(text: string): TextTableBlock[] {
  if (!text) return [];

  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: TextTableBlock[] = [];
  let textBuf: string[] = [];
  let tableBuf: string[] = [];

  const flushText = () => {
    if (textBuf.length === 0) return;
    blocks.push({ type: "text", content: textBuf.join("\n") });
    textBuf = [];
  };

  const flushTable = () => {
    if (tableBuf.length === 0) return;
    const table = parseTableLines(tableBuf);
    if (table) {
      blocks.push({ type: "table", header: table.header, rows: table.rows });
    } else {
      textBuf.push(...tableBuf);
    }
    tableBuf = [];
  };

  for (const line of lines) {
    if (isTableLine(line)) {
      flushText();
      tableBuf.push(line);
    } else {
      flushTable();
      textBuf.push(line);
    }
  }
  flushTable();
  flushText();

  return blocks.length > 0 ? blocks : [{ type: "text", content: text }];
}
