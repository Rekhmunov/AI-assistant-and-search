import {
  IMAGE_COMPRESS_THRESHOLD_BYTES,
  IMAGE_MAX_EDGE_PX,
  isImageFile,
} from "../constants/files";

/**
 * Downscale large photos before upload to stay within size limits and speed up OCR.
 */
export async function prepareFileForUpload(file: File): Promise<File> {
  if (!isImageFile(file)) return file;
  if (file.size <= IMAGE_COMPRESS_THRESHOLD_BYTES) return file;
  if (typeof createImageBitmap !== "function") return file;

  let bitmap: ImageBitmap | null = null;
  try {
    bitmap = await createImageBitmap(file);
    const scale = Math.min(1, IMAGE_MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height));
    if (scale >= 1 && file.size <= IMAGE_COMPRESS_THRESHOLD_BYTES) {
      return file;
    }

    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, w, h);

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((b) => resolve(b), "image/jpeg", 0.85);
    });
    if (!blob) return file;

    const base = file.name.replace(/\.[^.]+$/, "") || "photo";
    return new File([blob], `${base}.jpg`, { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return file;
  } finally {
    bitmap?.close();
  }
}
