const CITATION_RE = /\[\d+\]/g;

function normalizeBodySpacing(body: string): string {
  return body
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([,.;:!?…])/g, "$1")
    .trimEnd();
}

export type ParagraphWithCitations = {
  text: string;
  indices: number[];
};

/** Объединяет индексы источников без дубликатов, сохраняя порядок. */
export function mergeCitationIndices(...lists: number[][]): number[] {
  const out: number[] = [];
  for (const list of lists) {
    for (const n of list) {
      if (!out.includes(n)) out.push(n);
    }
  }
  return out;
}

/** Убирает [N] из текста и возвращает индексы источников для чипов. */
export function parseParagraphCitations(paragraph: string): ParagraphWithCitations {
  const indices: number[] = [];

  const body = paragraph.replace(CITATION_RE, (match) => {
    const num = Number.parseInt(match.slice(1, -1), 10);
    if (Number.isFinite(num) && !indices.includes(num)) {
      indices.push(num);
    }
    return "";
  });

  return { text: normalizeBodySpacing(body), indices };
}

/** Убирает маркеры [N] из текста (для копирования и финального текста). */
export function stripCitationMarkers(text: string): string {
  if (!text || !text.includes("[")) return text;
  return text
    .split(/\n\n+/)
    .map((paragraph) => parseParagraphCitations(paragraph).text)
    .join("\n\n");
}
