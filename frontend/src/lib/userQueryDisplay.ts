/** Убирает служебный хвост «[Файлы: …]» из текста вопроса (чипы вложений показывают имена). */
export function stripUserQueryDisplay(content: string): string {
  const trimmed = content.trimEnd();
  const withoutFiles = trimmed.replace(/\n\n\[Файлы:[^\]]*\]\s*$/u, "");
  return withoutFiles.trimEnd();
}
