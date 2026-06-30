/**
 * Скачивание изображения с учётом среды:
 * - MAX mini-app (WebView): <a download> не работает → navigator.share({ files })
 * - Десктоп / браузер: стандартный <a download> с blob URL
 */
import { isMaxWebApp } from "./maxApp";

export async function downloadImageBlob(src: string, filename: string): Promise<void> {
  // Получаем blob (src может быть blob: URL или https:)
  let blob: Blob;
  if (src.startsWith("blob:")) {
    const resp = await fetch(src);
    blob = await resp.blob();
  } else {
    const resp = await fetch(src);
    blob = await resp.blob();
  }

  // В MAX mini-app используем navigator.share — это единственный надёжный способ
  // сохранить файл в галерею через WebView (window.WebApp.downloadFile открывает share, не скачивает)
  if (isMaxWebApp() && typeof navigator.share === "function") {
    try {
      const file = new File([blob], filename, { type: blob.type || "image/jpeg" });
      if (typeof navigator.canShare === "function" && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file], title: filename });
        return;
      }
    } catch {
      // пользователь отменил или share недоступен → fallthrough к anchor
    }
  }

  // Стандартное скачивание через <a download>
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
}

export function buildImageFilename(title: string | undefined): string {
  const raw = (title || "generated-image").trim();
  const safe = raw.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 80) || "image";
  return safe.endsWith(".jpg") || safe.endsWith(".png") ? safe : `${safe}.jpg`;
}
