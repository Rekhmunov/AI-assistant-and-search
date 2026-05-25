/** MIME and extensions accepted for document analysis (v1). */
export const ACCEPT_FILE_INPUT =
  ".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv";

export const MAX_FILE_BYTES_FREE = 10 * 1024 * 1024;
export const MAX_FILE_BYTES_PRO = 20 * 1024 * 1024;

const EXT_OK = new Set([
  "txt",
  "md",
  "json",
  "csv",
  "pdf",
  "docx",
  "xlsx",
  "xls",
]);

export function validateFile(file: File, maxBytes: number): string | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!EXT_OK.has(ext)) {
    return "Формат не поддерживается. Используйте PDF, Word, Excel, CSV или текст.";
  }
  if (file.size > maxBytes) {
    return `Файл слишком большой (макс. ${Math.round(maxBytes / 1024 / 1024)} МБ)`;
  }
  return null;
}
