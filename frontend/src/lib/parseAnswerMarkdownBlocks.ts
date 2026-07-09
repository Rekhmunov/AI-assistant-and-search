export type AnswerMarkdownBlock =
  | { type: "heading"; level: 1 | 2 | 3 | 4 | 5 | 6; text: string }
  | { type: "paragraph"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "blockquote"; lines: string[] }
  | { type: "hr" };

const HEADING_RE = /^(#{1,6})\s+(.+)$/;
const UL_RE = /^[*+\-]\s+(.+)$/;
const OL_RE = /^\d+[.)]\s+(.+)$/;
const BOLD_ONLY_RE = /^\*\*(.+)\*\*$/;
const UNDERONLY_RE = /^__(.+)__$/;
const BLOCKQUOTE_RE = /^>\s*(.*)/;
const HR_RE = /^([*\-_])\s*\1\s*\1[\s\1]*$/;

function isBlockStarter(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return false;
  return (
    HEADING_RE.test(trimmed) ||
    UL_RE.test(trimmed) ||
    OL_RE.test(trimmed) ||
    BOLD_ONLY_RE.test(trimmed) ||
    UNDERONLY_RE.test(trimmed) ||
    BLOCKQUOTE_RE.test(trimmed) ||
    HR_RE.test(trimmed)
  );
}

function normalizeHeadingText(text: string): string {
  return text.replace(/^\d+[.)]\s+/, "").trim();
}

function parseHeadingBlock(line: string): { level: 1|2|3|4|5|6; text: string } | null {
  const trimmed = line.trim();
  const hash = trimmed.match(HEADING_RE);
  if (hash) {
    const level = Math.min(hash[1].length, 6) as 1|2|3|4|5|6;
    return { level, text: normalizeHeadingText(hash[2]) };
  }
  const bold = trimmed.match(BOLD_ONLY_RE);
  if (bold) return { level: 3, text: normalizeHeadingText(bold[1]) };
  const under = trimmed.match(UNDERONLY_RE);
  if (under) return { level: 3, text: normalizeHeadingText(under[1]) };
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

    // Horizontal rule: ---, ***, ___
    if (HR_RE.test(lines[i].trim())) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    const heading = parseHeadingBlock(lines[i]);
    if (heading) {
      blocks.push({ type: "heading", level: heading.level, text: heading.text });
      i += 1;
      continue;
    }

    // Blockquote
    if (BLOCKQUOTE_RE.test(lines[i].trim())) {
      const bqLines: string[] = [];
      while (i < lines.length) {
        const bqMatch = lines[i].trim().match(BLOCKQUOTE_RE);
        if (bqMatch) {
          bqLines.push(bqMatch[1]);
          i += 1;
        } else {
          break;
        }
      }
      if (bqLines.length) blocks.push({ type: "blockquote", lines: bqLines });
      continue;
    }

    const trimmed = lines[i].trim();
    const ulMatch = trimmed.match(UL_RE);
    const olMatch = trimmed.match(OL_RE);

    if (olMatch) {
    const nextTrimmed = i + 1 < lines.length ? lines[i + 1].trim() : "";
        if (!OL_RE.test(nextTrimmed)) {
        blocks.push({ type: "heading", level: 3, text: normalizeHeadingText(olMatch[1]) });
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
