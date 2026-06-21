/** MIME and extensions accepted for document analysis. */
export const ACCEPT_DOCUMENT_INPUT =
  ".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/plain,text/csv";

export const ACCEPT_IMAGE_INPUT =
  "image/jpeg,image/png,image/webp,image/heic,image/heif,.jpg,.jpeg,.png,.webp,.heic,.heif";

export const ACCEPT_FILE_INPUT = `${ACCEPT_DOCUMENT_INPUT},${ACCEPT_IMAGE_INPUT}`;

export const MAX_ATTACHMENTS = 10;

/** Sync with backend app.constants.attachments */
export const MAX_FILE_BYTES_FREE = 8 * 1024 * 1024;
export const MAX_FILE_BYTES_PRO = 15 * 1024 * 1024;

/** Client-side: compress photos above this before upload. */
export const IMAGE_COMPRESS_THRESHOLD_BYTES = 1_500_000;
export const IMAGE_MAX_EDGE_PX = 2048;

const DOCUMENT_EXT = new Set(["txt", "md", "json", "csv", "pdf", "docx", "xlsx", "xls"]);
const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "webp", "heic", "heif"]);

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

/** Sniff image format from magic bytes (MAX WebView often omits name/MIME). */
export function sniffImageExt(data: Uint8Array): string | null {
  if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) return "jpg";
  if (
    data.length >= 8 &&
    data[0] === 0x89 &&
    data[1] === 0x50 &&
    data[2] === 0x4e &&
    data[3] === 0x47
  ) {
    return "png";
  }
  if (data.length >= 12 && data[0] === 0x52 && data[1] === 0x49 && data[2] === 0x46 && data[3] === 0x46) {
    if (data[8] === 0x57 && data[9] === 0x45 && data[10] === 0x42 && data[11] === 0x50) return "webp";
  }
  if (data.length >= 12 && data[4] === 0x66 && data[5] === 0x74 && data[6] === 0x79 && data[7] === 0x70) {
    const brand = String.fromCharCode(data[8], data[9], data[10], data[11]);
    if (["heic", "heix", "hevc", "mif1", "msf1", "heif"].includes(brand)) return "heic";
  }
  return null;
}

export async function sniffFileKind(file: File): Promise<FileKind | null> {
  if (file.size < 4) return null;
  const buf = await file.slice(0, 16).arrayBuffer();
  return sniffImageExt(new Uint8Array(buf)) ? "image" : null;
}

/** Resolve kind from name/MIME, byte sniff, or picker hint (MAX). */
export async function resolveFileKind(file: File, expected?: FileKind): Promise<FileKind | null> {
  const fromMeta = fileKind(file);
  if (fromMeta) return fromMeta;
  const fromSniff = await sniffFileKind(file);
  if (fromSniff) return fromSniff;
  if (expected) return expected;
  return null;
}

export function validateFile(
  file: File,
  maxBytes: number,
  plan: "free" | "pro" | undefined,
  expected?: FileKind,
  resolvedKind?: FileKind | null,
): FileValidationResult | null {
  const kind = resolvedKind ?? fileKind(file);
  if (!kind) {
    return {
      message:
        "Формат не поддерживается. Используйте PDF, Word, Excel, CSV, текст или фото (JPEG, PNG, WebP, HEIC).",
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
  proMaxBytes?: number,
): FileValidationResult {
  const limitMb = Math.round(maxBytes / 1024 / 1024);
  const fileMb = (file.size / (1024 * 1024)).toFixed(1);
  const proMb = Math.round((proMaxBytes ?? MAX_FILE_BYTES_PRO) / 1024 / 1024);
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
