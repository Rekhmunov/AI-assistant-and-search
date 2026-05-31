export type AnswerMarkdownBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] };

const HEADING_RE = /^#{1,6}\s+(.+)$/;
const UL_RE = /^[*+\-]\s+(.+)$/;
const OL_RE = /^\d+[.)]\s+(.+)$/;
const BOLD_ONLY_RE = /^\*\*(.+)\*\*$/;
const UNDERONLY_RE = /^__(.+)__$/;

function isBlockStarter(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  return (
    HEADING_RE.test(trimmed) ||
    UL_RE.test(trimmed) ||
    OL_RE.test(trimmed) ||
    BOLD_ONLY_RE.test(trimmed) ||
    UNDERONLY_RE.test(trimmed)
  );
}

function normalizeHeadingText(text: string): string {
  return text.replace(/^\d+[.)]\s+/, "").trim();
}

function parseHeading(line: string): string | null {
  const trimmed = line.trim();
  const hash = trimmed.match(HEADING_RE);
  if (hash) return normalizeHeadingText(hash[1]);
  const bold = trimmed.match(BOLD_ONLY_RE);
  if (bold) return normalizeHeadingText(bold[1]);
  const under = trimmed.match(UNDERONLY_RE);
  if (under) return normalizeHeadingText(under[1]);
  return null;
}

/** Разбирает markdown-блоки ответа: заголовки, абзацы, списки. */
export function parseAnswerMarkdownBlocks(text: string): AnswerMarkdownBlock[] {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const lines = normalized.split("\n");
  const blocks: AnswerMarkdownBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    while (i < lines.length && !lines[i].trim()) i += 1;
    if (i >= lines.length) break;

    const heading = parseHeading(lines[i]);
    if (heading) {
      blocks.push({ type: "heading", text: heading });
      i += 1;
      continue;
    }

    const trimmed = lines[i].trim();
    const ulMatch = trimmed.match(UL_RE);
    const olMatch = trimmed.match(OL_RE);

    if (olMatch) {
      const nextTrimmed = i + 1 < lines.length ? lines[i + 1].trim() : "";
      if (!OL_RE.test(nextTrimmed)) {
        blocks.push({ type: "heading", text: normalizeHeadingText(olMatch[1]) });
        i += 1;
        continue;
      }
      const items: string[] = [];
      while (i < lines.length) {
        const line = lines[i].trim();
        if (!line) break;
        const om = line.match(OL_RE);
        if (om) {
          items.push(om[1].trim());
          i += 1;
        } else {
          break;
        }
      }
      if (items.length) {
        blocks.push({ type: "ol", items });
      }
      continue;
    }

    if (ulMatch) {
      const items: string[] = [];
      while (i < lines.length) {
        const line = lines[i].trim();
        if (!line) break;
        const um = line.match(UL_RE);
        if (um) {
          items.push(um[1].trim());
          i += 1;
        } else {
          break;
        }
      }
      if (items.length) {
        blocks.push({ type: "ul", items });
      }
      continue;
    }

    const paragraphLines: string[] = [];
    while (i < lines.length) {
      const line = lines[i];
      const t = line.trim();
      if (!t) break;
      if (isBlockStarter(t)) break;
      paragraphLines.push(t);
      i += 1;
    }
    if (paragraphLines.length) {
      blocks.push({ type: "paragraph", text: paragraphLines.join("\n") });
    }
  }

  return blocks;
}
