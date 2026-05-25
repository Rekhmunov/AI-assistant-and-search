import type { ReactNode } from "react";
import type { Source } from "../api/client";

/** Разбивает текст с [1], [2] на фрагменты со ссылками на источники. */
export function renderTextWithCitations(text: string, sources: Source[]): ReactNode[] {
  if (!text) return [];

  const byIndex = new Map(sources.map((s) => [s.index, s]));
  const re = /\[(\d+)\]/g;
  const parts: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const num = Number.parseInt(match[1], 10);
    const src = byIndex.get(num);
    if (src?.url) {
      parts.push(
        <a
          key={`cite-${key++}`}
          href={src.url}
          target="_blank"
          rel="noopener noreferrer"
          className="cite-link"
          title={src.title || src.domain}
        >
          [{num}]
        </a>,
      );
    } else {
      parts.push(match[0]);
    }
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push(text.slice(last));
  }

  return parts.length ? parts : [text];
}
