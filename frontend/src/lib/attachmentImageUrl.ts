/** URL контента загруженного/сгенерированного файла на нашем API. */
export function isProtectedFileContentUrl(url: string | null | undefined): boolean {
  const u = (url || "").trim();
  if (!u) return false;
  return /\/api\/files\/[0-9a-f-]{36}\/content/i.test(u);
}

export function fileContentPath(fileId: string): string {
  return `/api/files/${fileId}/content`;
}
