/** Одиночное скачивание по URL (без fetch+blob — иначе часть браузеров качает дважды). */

let inflightKey: string | null = null;

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
