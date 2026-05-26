/**
 * Убирает markdown в текстовых фрагментах (без fenced code — их рендерит AnswerBody).
 */
export function formatMarkdownText(text: string): string {
  if (!text) return "";

  let s = text.replace(/\r\n/g, "\n");

  s = s.replace(/^#{1,6}\s+(.+)$/gm, "\n$1\n");
  s = s.replace(/\*\*([^*]+)\*\*/g, "$1");
  s = s.replace(/__([^_]+)__/g, "$1");
  s = s.replace(/(?<!\w)\*([^*\n]+)\*(?!\w)/g, "$1");
  s = s.replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "$1");
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  s = s.replace(/^[*\-_]{3,}\s*$/gm, "");

  s = s
    .split("\n")
    .map((line) => line.replace(/\s+$/g, ""))
    .join("\n");

  return s.replace(/\n{3,}/g, "\n\n");
}
