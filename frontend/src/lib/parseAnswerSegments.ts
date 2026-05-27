import { splitTextWithUnfencedCode } from "./extractUnfencedCode";

export type AnswerSegment =
  | { type: "text"; content: string }
  | { type: "code"; content: string; lang?: string; partial?: boolean };

function expandTextSegments(segments: AnswerSegment[]): AnswerSegment[] {
  const out: AnswerSegment[] = [];
  for (const seg of segments) {
    if (seg.type === "code") {
      out.push(seg);
      continue;
    }
    out.push(...splitTextWithUnfencedCode(seg.content));
  }
  return out;
}

/**
 * Делит ответ на текст и fenced-блоки ```…``` (код, JSON, TXT и т.д.).
 * Незакрытый ``` в конце (стрим) — code с partial: true.
 * В тексте также ищет «голый» PHP/HTML/команды терминала.
 */
export function parseAnswerSegments(raw: string): AnswerSegment[] {
  if (!raw) return [];

  const text = raw.replace(/\r\n/g, "\n");
  const segments: AnswerSegment[] = [];
  const closedRe = /```[ \t]*([\w-]*)?[ \t]*\r?\n([\s\S]*?)```/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = closedRe.exec(text)) !== null) {
    if (match.index > last) {
      segments.push({ type: "text", content: text.slice(last, match.index) });
    }
    const lang = match[1]?.trim().toLowerCase() || undefined;
    segments.push({
      type: "code",
      content: match[2].replace(/\n$/, ""),
      lang: lang || undefined,
    });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    const tail = text.slice(last);
    const openAt = tail.indexOf("```");
    if (openAt >= 0) {
      if (openAt > 0) {
        segments.push({ type: "text", content: tail.slice(0, openAt) });
      }
      const afterFence = tail.slice(openAt + 3);
      const langMatch = afterFence.match(/^([\w-]*)[ \t]*\r?\n?/);
      const lang = langMatch?.[1]?.trim().toLowerCase() || undefined;
      const code = langMatch ? afterFence.slice(langMatch[0].length) : afterFence;
      segments.push({ type: "code", content: code, lang, partial: true });
    } else {
      segments.push({ type: "text", content: tail });
    }
  }

  const base = segments.length > 0 ? segments : [{ type: "text", content: text }];
  return expandTextSegments(base);
}
