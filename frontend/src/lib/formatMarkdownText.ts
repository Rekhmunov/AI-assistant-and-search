/**
 * Минимальная очистка текста: убирает горизонтальные разделители.
 * Bold/italic/links теперь рендерятся через renderInlineContent, не стрипаются.
 * Используется только для форматирования plain-text фрагментов (не markdown).
 */
export function formatMarkdownText(text: string): string {
  if (!text) return "";
  let s = text.replace(/\r\n/g, "\n");
  // Убираем горизонтальные разделители (---  ***  ___)
  s = s.replace(/^[*\-_]{3,}\s*$/gm, "");
  s = s
    .split("\n")
    .map((line) => line.replace(/\s+$/g, ""))
    .join("\n");
  return s.replace(/\n{3,}/g, "\n\n");
}
