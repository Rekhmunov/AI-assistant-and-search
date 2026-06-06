/** Открыть внешнюю ссылку в новой вкладке (оплата, MAX-бот и т.п.). */
export function openExternalUrl(url: string): boolean {
  const opened = window.open(url, "_blank", "noopener,noreferrer");
  return opened != null;
}
