import { formatMarkdownText } from "./formatMarkdownText";
import { formatChartSpecForCopy, parseChartSpec } from "./parseChartSpec";
import { parseAnswerSegments } from "./parseAnswerSegments";
import { stripCitationMarkers } from "./paragraphCitations";

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
      if (!inner) continue;
      const lang = seg.lang?.trim().toLowerCase();
      if (lang === "chart") {
        const spec = parseChartSpec(inner);
        parts.push(spec ? formatChartSpecForCopy(spec) : inner);
      } else {
        parts.push(inner);
      }
    } else {
      const formatted = stripCitationMarkers(formatMarkdownText(seg.content)).trim();
      if (formatted) parts.push(formatted);
    }
  }

  return parts.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
}
