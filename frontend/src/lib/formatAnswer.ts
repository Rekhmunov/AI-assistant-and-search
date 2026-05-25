/**
 * Убирает markdown-разметку из ответа LLM для отображения в миниаппе.
 * Сохраняет абзацы, нумерованные списки и логику текста.
 */
export function formatAnswerForDisplay(text: string): string {
  if (!text) return "";

  let s = text.replace(/\r\n/g, "\n");

  // Блоки кода
  s = s.replace(/```[\s\S]*?```/g, (block) => {
    const inner = block.replace(/^```\w*\n?/, "").replace(/```$/, "").trim();
    return inner ? `\n${inner}\n` : "\n";
  });

  // Заголовки # … ######
  s = s.replace(/^#{1,6}\s+(.+)$/gm, "\n$1\n");

  // Жирный / курсив
  s = s.replace(/\*\*([^*]+)\*\*/g, "$1");
  s = s.replace(/__([^_]+)__/g, "$1");
  s = s.replace(/(?<!\w)\*([^*\n]+)\*(?!\w)/g, "$1");
  s = s.replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "$1");

  // Ссылки [текст](url) → текст
  s = s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

  // Горизонтальные линии
  s = s.replace(/^[*\-_]{3,}\s*$/gm, "");

  // Лишние пробелы в строках
  s = s
    .split("\n")
    .map((line) => line.replace(/\s+$/g, ""))
    .join("\n");

  s = s.replace(/\n{3,}/g, "\n\n").trim();

  return s;
}
