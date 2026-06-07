const GENERIC_PASTE_NAMES = new Set(["", "image.png", "image.jpeg", "image.jpg", "blob"]);

function extensionForMime(mime: string): string {
  if (mime === "image/jpeg") return "jpg";
  if (mime === "image/png") return "png";
  if (mime === "image/webp") return "webp";
  if (mime === "image/heic") return "heic";
  if (mime === "image/heif") return "heif";
  const tail = mime.split("/")[1];
  return tail?.replace("jpeg", "jpg") || "png";
}

export function normalizePastedImageFile(file: File, index: number): File {
  const mime = file.type || "image/png";
  const base = file.name.trim().toLowerCase();
  const hasName = base && !GENERIC_PASTE_NAMES.has(base);
  const name = hasName ? file.name : `image-${Date.now()}-${index + 1}.${extensionForMime(mime)}`;
  if (name === file.name) return file;
  return new File([file], name, { type: mime });
}

/** Извлечь изображения из буфера (Ctrl+V / ПКМ «Вставить»). */
export function extractClipboardImages(data: DataTransfer | null): File[] {
  if (!data) return [];

  const files: File[] = [];
  const seen = new Set<File>();

  for (const item of data.items) {
    if (item.kind !== "file") continue;
    const file = item.getAsFile();
    if (!file || !file.type.startsWith("image/")) continue;
    if (seen.has(file)) continue;
    seen.add(file);
    files.push(normalizePastedImageFile(file, files.length));
  }

  if (!files.length && data.files.length) {
    for (const file of Array.from(data.files)) {
      if (!file.type.startsWith("image/")) continue;
      files.push(normalizePastedImageFile(file, files.length));
    }
  }

  return files;
}

export function filesToFileList(files: File[]): FileList {
  const dt = new DataTransfer();
  for (const file of files) dt.items.add(file);
  return dt.files;
}
