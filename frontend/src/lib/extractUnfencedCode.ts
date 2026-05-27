import type { AnswerSegment } from "./parseAnswerSegments";

type FoundBlock = { start: number; end: number; content: string; lang?: string };

/** Выделяет код без ``` (LLM часто пишет «без markdown»). */
function findUnfencedBlocks(text: string): FoundBlock[] {
  const found: FoundBlock[] = [];
  let m: RegExpExecArray | null;

  const introCodeRe =
    /(?:следующ(?:ий|ему)\s+код|пример\s+кода|создайте\s+файл|поместите\s+в\s+(?:него|файл)|код\s+(?:ниже|файла)|вот\s+код)[^\n]*\n+([\s\S]*?)(?=\n\n[A-Za-zА-Яа-яЁё]|\n\d+\.\s|$)/gi;
  while ((m = introCodeRe.exec(text)) !== null) {
    const body = m[1].trim();
    if (body.length >= 8 && looksLikeCode(body) && !overlaps(found, m.index, m.index + m[0].length)) {
      const lang = body.includes("<?php") ? "php" : body.includes("def ") ? "python" : "txt";
      found.push({
        start: m.index + m[0].indexOf(body),
        end: m.index + m[0].indexOf(body) + body.length,
        content: body,
        lang,
      });
    }
  }

  const phpRe = /<\?php[\s\S]*?\?>/g;
  while ((m = phpRe.exec(text)) !== null) {
    found.push({ start: m.index, end: m.index + m[0].length, content: m[0], lang: "php" });
  }

  const htmlOpenRe =
    /<(html|head|body|div|script|style|table|form|!DOCTYPE)[\s>][\s\S]*?<\/\1>/gi;
  while ((m = htmlOpenRe.exec(text)) !== null) {
    if (!overlaps(found, m.index, m.index + m[0].length)) {
      found.push({ start: m.index, end: m.index + m[0].length, content: m[0], lang: "html" });
    }
  }

  const lines = text.split("\n");
  let lineOff = 0;
  let runStart = -1;
  let runLines: string[] = [];

  const flushRun = (endOff: number) => {
    if (runLines.length === 0) return;
    const content = runLines.join("\n");
    const start = runStart;
    const end = endOff;
    if (content.trim().length >= 4 && !overlaps(found, start, end)) {
      found.push({ start, end, content, lang: "bash" });
    }
    runStart = -1;
    runLines = [];
  };

  const cmdRe =
    /^(php|npm|yarn|pnpm|docker|kubectl|curl|wget|git|pip3?|composer|python3?|node|cargo|go|make|bash|sh)\s+/i;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    const lineStart = lineOff;
    const lineEnd = lineOff + line.length;

    if (trimmed && cmdRe.test(trimmed)) {
      if (runStart < 0) runStart = lineStart;
      runLines.push(line);
    } else if (runLines.length > 0 && !trimmed) {
      runLines.push(line);
    } else {
      if (runLines.length > 0) {
        flushRun(lineStart);
      }
    }
    lineOff += line.length + 1;
  }
  if (runLines.length > 0) {
    flushRun(text.length);
  }

  found.sort((a, b) => a.start - b.start);
  return found;
}

function overlaps(blocks: FoundBlock[], start: number, end: number): boolean {
  return blocks.some((b) => start < b.end && end > b.start);
}

function looksLikeCode(body: string): boolean {
  const lines = body.split("\n").filter((l) => l.trim());
  if (lines.length === 0) return false;
  const codey =
    /<\?php|^\s*(def |class |import |from |const |let |var |function |#include|public |private |echo |print\(|SELECT |INSERT )/im;
  return codey.test(body) || lines.some((l) => /[{};]=/.test(l) && !/^[А-Яа-яЁё]/.test(l.trim()));
}

export function splitTextWithUnfencedCode(text: string): AnswerSegment[] {
  if (!text) return [];

  const blocks = findUnfencedBlocks(text);
  if (blocks.length === 0) {
    return [{ type: "text", content: text }];
  }

  const segments: AnswerSegment[] = [];
  let pos = 0;

  for (const block of blocks) {
    if (block.start > pos) {
      segments.push({ type: "text", content: text.slice(pos, block.start) });
    }
    segments.push({ type: "code", content: block.content.trim(), lang: block.lang });
    pos = block.end;
  }

  if (pos < text.length) {
    segments.push({ type: "text", content: text.slice(pos) });
  }

  return segments;
}
