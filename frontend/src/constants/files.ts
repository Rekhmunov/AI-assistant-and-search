/** MIME and extensions accepted for document analysis. */
export const ACCEPT_DOCUMENT_INPUT =
  ".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv";

export const ACCEPT_IMAGE_INPUT = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp";

export const ACCEPT_FILE_INPUT = `${ACCEPT_DOCUMENT_INPUT},${ACCEPT_IMAGE_INPUT}`;

export const MAX_ATTACHMENTS = 10;

/** Sync with backend app.constants.attachments */
export const MAX_FILE_BYTES_FREE = 8 * 1024 * 1024;
export const MAX_FILE_BYTES_PRO = 15 * 1024 * 1024;

/** Client-side: compress photos above this before upload. */
export const IMAGE_COMPRESS_THRESHOLD_BYTES = 1_500_000;
export const IMAGE_MAX_EDGE_PX = 2048;

const DOCUMENT_EXT = new Set(["txt", "md", "json", "csv", "pdf", "docx", "xlsx", "xls"]);
const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "webp"]);

export type FileKind = "document" | "image";

export type FileValidationResult = {
  message: string;
  suggestPro: boolean;
};

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
  plan: "free" | "pro" | undefined,
  expected?: FileKind,
): FileValidationResult | null {
  const kind = fileKind(file);
  if (!kind) {
    return {
      message:
        "Формат не поддерживается. Используйте PDF, Word, Excel, CSV, текст или фото (JPEG, PNG, WebP).",
      suggestPro: false,
    };
  }
  if (expected && kind !== expected) {
    return {
      message:
        expected === "image"
          ? "Выберите фото (JPEG, PNG или WebP)."
          : "Выберите документ (PDF, Word, Excel, CSV или текст).",
      suggestPro: false,
    };
  }
  if (file.size > maxBytes) {
    return fileSizeError(file, maxBytes, plan);
  }
  return null;
}

export function fileSizeError(
  file: File,
  maxBytes: number,
  plan: "free" | "pro" | undefined,
): FileValidationResult {
  const limitMb = Math.round(maxBytes / 1024 / 1024);
  const fileMb = (file.size / (1024 * 1024)).toFixed(1);
  const proMb = Math.round(MAX_FILE_BYTES_PRO / 1024 / 1024);
  if (plan === "free") {
    return {
      message: `«${file.name}» (${fileMb} МБ) — лимит Free ${limitMb} МБ. Перейдите на Pro (до ${proMb} МБ на файл).`,
      suggestPro: true,
    };
  }
  return {
    message: `«${file.name}» (${fileMb} МБ) превышает лимит ${limitMb} МБ.`,
    suggestPro: false,
  };
}

export function isImageFile(file: File): boolean {
  return fileKind(file) === "image";
}
