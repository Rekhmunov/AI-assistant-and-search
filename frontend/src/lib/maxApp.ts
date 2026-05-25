/** True when opened inside MAX miniapp (WebApp bridge present). */
export function isMaxWebApp(): boolean {
  return typeof window !== "undefined" && Boolean(window.WebApp?.initData?.trim());
}

export function getMaxInitData(): string {
  return window.WebApp?.initData?.trim() ?? "";
}

/** Deep link to open bot / miniapp (set VITE_MAX_BOT_URL in build). */
export function getMaxBotUrl(): string {
  const url = import.meta.env.VITE_MAX_BOT_URL?.trim();
  return url || "https://max.ru";
}
