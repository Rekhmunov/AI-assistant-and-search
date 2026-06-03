/** Безопасная строка ответа ассистента (SSE/API иногда отдают не string). */
export function normalizeAnswerText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

export function answerHasText(value: unknown): boolean {
  return normalizeAnswerText(value).trim().length > 0;
}
