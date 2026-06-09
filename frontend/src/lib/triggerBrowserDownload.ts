import { isMaxWebApp } from "./maxApp";

/** Одиночное скачивание по URL (без fetch+blob — иначе часть браузеров качает дважды). */

let inflightKey: string | null = null;

function toAbsoluteHttpsUrl(url: string): string {
  const trimmed = url.trim();
  if (trimmed.startsWith("https://")) return trimmed;
  if (trimmed.startsWith("http://")) return `https://${trimmed.slice("http://".length)}`;
  const origin =
    typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "https://glosix.ru";
  return `${origin}${trimmed.startsWith("/") ? trimmed : `/${trimmed}`}`;
}

export function triggerBrowserDownloadOnce(url: string, filename: string): void {
  const key = `${url}\0${filename}`;
  if (inflightKey === key) return;
  inflightKey = key;

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "document";
  anchor.rel = "noopener noreferrer";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);

  window.setTimeout(() => {
    if (inflightKey === key) inflightKey = null;
  }, 2500);
}

/** Скачивание по https-ссылке: в MAX — нативный downloadFile, иначе anchor.download. */
export async function downloadRemoteFile(url: string, filename: string): Promise<void> {
  const absoluteUrl = toAbsoluteHttpsUrl(url);
  const name = filename.trim() || "document";

  if (isMaxWebApp() && window.WebApp?.downloadFile) {
    await window.WebApp.downloadFile(absoluteUrl, name);
    return;
  }

  triggerBrowserDownloadOnce(absoluteUrl, name);
}
