import { formatMarkdownText } from "./formatMarkdownText";
import { parseAnswerSegments } from "./parseAnswerSegments";

/**
 * Плоский текст для копирования всего ответа (без markdown, код как текст).
 */
export function formatAnswerForDisplay(text: string): string {
  if (!text) return "";

  const segments = parseAnswerSegments(text);
  const parts: string[] = [];

  for (const seg of segments) {
    if (seg.type === "code") {
      const inner = seg.content.trim();
      if (inner) parts.push(inner);
    } else {
      const formatted = formatMarkdownText(seg.content).trim();
      if (formatted) parts.push(formatted);
    }
  }

  return parts.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
}
