/** Переносит [1], [2] … в конец абзаца (не в середине фразы). */
const CITATION_RE = /\[\d+\]/g;

function dedupeCitations(matches: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of matches) {
    if (!seen.has(m)) {
      seen.add(m);
      out.push(m);
    }
  }
  return out;
}

function normalizeBodySpacing(body: string): string {
  return body
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([,.;:!?…])/g, "$1")
    .trimEnd();
}

function attachCitations(body: string, citations: string[]): string {
  if (!citations.length) return body;
  const trail = citations.join("");
  const trimmed = body.trimEnd();
  if (!trimmed) return trail;

  const punctMatch = trimmed.match(/^(.*?)([.!?…]+)$/);
  if (punctMatch) {
    const core = punctMatch[1].trimEnd();
    const punct = punctMatch[2];
    return core ? `${core} ${trail}${punct}` : `${trail}${punct}`;
  }
  return `${trimmed} ${trail}`;
}

function processParagraph(paragraph: string): string {
  if (!/\[\d+\]/.test(paragraph)) {
    return paragraph;
  }

  const found: string[] = [];
  const body = paragraph.replace(CITATION_RE, (match) => {
    found.push(match);
    return "";
  });

  return attachCitations(normalizeBodySpacing(body), dedupeCitations(found));
}

/**
 * Обрабатывает текст по абзацам (разделитель — пустая строка).
 * Блоки кода не трогаем — вызывать только для текстовых сегментов.
 */
export function moveCitationsToParagraphEnds(text: string): string {
  if (!text || !text.includes("[")) return text;
  return text
    .split(/\n\n+/)
    .map((p) => processParagraph(p))
    .join("\n\n");
}
