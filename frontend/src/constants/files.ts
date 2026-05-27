/** MIME and extensions accepted for document analysis. */
export const ACCEPT_DOCUMENT_INPUT =
  ".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv";

export const ACCEPT_IMAGE_INPUT = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp";

export const ACCEPT_FILE_INPUT = `${ACCEPT_DOCUMENT_INPUT},${ACCEPT_IMAGE_INPUT}`;

export const MAX_ATTACHMENTS = 10;

export const MAX_FILE_BYTES_FREE = 10 * 1024 * 1024;
export const MAX_FILE_BYTES_PRO = 20 * 1024 * 1024;

/** Client-side: compress photos above this before upload. */
export const IMAGE_COMPRESS_THRESHOLD_BYTES = 1_500_000;
export const IMAGE_MAX_EDGE_PX = 2048;

const DOCUMENT_EXT = new Set(["txt", "md", "json", "csv", "pdf", "docx", "xlsx", "xls"]);
const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "webp"]);

export type FileKind = "document" | "image";

export function fileKind(file: File): FileKind | null {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (DOCUMENT_EXT.has(ext)) return "document";
  if (IMAGE_EXT.has(ext)) return "image";
  if (file.type.startsWith("image/")) return "image";
  return null;
}

export function validateFile(
  file: File,
  maxBytes: number,
  expected?: FileKind,
): string | null {
  const kind = fileKind(file);
  if (!kind) {
    return "Формат не поддерживается. Используйте PDF, Word, Excel, CSV, текст или фото (JPEG, PNG, WebP).";
  }
  if (expected && kind !== expected) {
    return expected === "image"
      ? "Выберите фото (JPEG, PNG или WebP)."
      : "Выберите документ (PDF, Word, Excel, CSV или текст).";
  }
  if (file.size > maxBytes) {
    return `Файл слишком большой (макс. ${Math.round(maxBytes / 1024 / 1024)} МБ)`;
  }
  return null;
}

export function isImageFile(file: File): boolean {
  return fileKind(file) === "image";
}
