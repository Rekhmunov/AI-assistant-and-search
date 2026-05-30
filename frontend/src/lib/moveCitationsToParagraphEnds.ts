import { parseParagraphCitations } from "./paragraphCitations";

/** Убирает маркеры [N] из текста (источники показываются чипами в UI). */
export function moveCitationsToParagraphEnds(text: string): string {
  if (!text || !text.includes("[")) return text;
  return text
    .split(/\n\n+/)
    .map((paragraph) => parseParagraphCitations(paragraph).text)
    .join("\n\n");
}
