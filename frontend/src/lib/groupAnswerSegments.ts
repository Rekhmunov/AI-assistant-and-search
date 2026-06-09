import type { AnswerSegment } from "./parseAnswerSegments";

export type GroupedAnswerSegment =
  | { type: "text"; content: string }
  | { type: "code"; content: string; lang?: string; partial?: boolean }
  | {
      type: "document";
      markdownParts: string[];
      charts: string[];
      partial?: boolean;
    };

function isMarkdownLang(lang?: string): boolean {
  const l = lang?.trim().toLowerCase();
  return l === "markdown" || l === "md";
}

function isChartLang(lang?: string): boolean {
  return lang?.trim().toLowerCase() === "chart";
}

function isBlankText(seg: AnswerSegment): boolean {
  return seg.type === "text" && !seg.content.trim();
}

function isBridgeText(seg: AnswerSegment): boolean {
  if (seg.type !== "text") return false;
  const t = seg.content.trim();
  return t.length > 0 && t.length <= 400;
}

/**
 * Склеивает цепочку markdown → chart → markdown в один блок документа с диаграммой.
 */
export function groupAnswerSegments(segments: AnswerSegment[]): GroupedAnswerSegment[] {
  const out: GroupedAnswerSegment[] = [];
  let i = 0;

  while (i < segments.length) {
    const seg = segments[i];
    if (seg.type === "text") {
      out.push(seg);
      i += 1;
      continue;
    }

    if (seg.partial || !isMarkdownLang(seg.lang) || !seg.content.trim()) {
      out.push(seg);
      i += 1;
      continue;
    }

    const markdownParts: string[] = [seg.content];
    const charts: string[] = [];
    let partial = Boolean(seg.partial);
    i += 1;

    while (i < segments.length) {
      while (i < segments.length && isBlankText(segments[i])) {
        i += 1;
      }
      if (i >= segments.length) break;

      const next = segments[i];

      if (next.type === "text" && isBridgeText(next)) {
        const peek = segments[i + 1];
        if (
          peek?.type === "code" &&
          !peek.partial &&
          (isChartLang(peek.lang) || isMarkdownLang(peek.lang)) &&
          peek.content.trim()
        ) {
          i += 1;
          continue;
        }
        if (charts.length > 0 || markdownParts.length > 1) {
          markdownParts.push(next.content.trim());
          i += 1;
          continue;
        }
        break;
      }

      if (next.type !== "code" || next.partial) break;

      if (!next.content.trim()) {
        i += 1;
        continue;
      }

      if (isChartLang(next.lang)) {
        charts.push(next.content);
        i += 1;
        continue;
      }

      if (isMarkdownLang(next.lang)) {
        markdownParts.push(next.content);
        i += 1;
        continue;
      }

      break;
    }

    if (charts.length > 0 || markdownParts.length > 1) {
      out.push({ type: "document", markdownParts, charts, partial });
    } else {
      out.push(seg);
    }
  }

  return out;
}
