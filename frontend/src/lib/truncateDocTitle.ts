/** Короткий заголовок документа в шапке блока (не упирается в кнопки). */
export function truncateDocTitle(title: string, maxLen = 34): string {
  const trimmed = title.trim().replace(/\s+/g, " ");
  if (trimmed.length <= maxLen) return trimmed;
  return `${trimmed.slice(0, maxLen - 1).trimEnd()}…`;
}
