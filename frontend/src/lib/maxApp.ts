/** True when opened inside MAX miniapp (WebApp bridge present). */
export function isMaxWebApp(): boolean {
  if (typeof window === "undefined") return false;
  const bridge = window.WebApp;
  if (!bridge) return false;
  return Boolean(bridge.initData?.trim() || bridge.platform?.trim());
}

/** MAX client platform: ios | android | desktop | web */
export function getMaxPlatform(): string {
  return window.WebApp?.platform?.trim().toLowerCase() ?? "";
}

export function isIosLikeDevice(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iPad|iPhone|iPod/i.test(navigator.userAgent);
}

export function getMaxInitData(): string {
  return window.WebApp?.initData?.trim() ?? "";
}

const BIND_START_PREFIX = "bind_";

/** startapp / WebAppStartParam from deeplink (?startapp=bind_…). */
export function getMaxStartParam(): string {
  if (typeof window === "undefined") return "";
  const fromBridge = window.WebApp?.initDataUnsafe?.start_param?.trim();
  if (fromBridge) return fromBridge;
  const params = new URLSearchParams(window.location.search);
  return params.get("WebAppStartParam")?.trim() ?? "";
}

export function parseMaxBindToken(startParam: string): string | null {
  const raw = startParam.trim();
  if (!raw.startsWith(BIND_START_PREFIX)) return null;
  const token = raw.slice(BIND_START_PREFIX.length).trim();
  return token || null;
}

/** Базовый URL бота без query (VITE_MAX_BOT_URL). */
export function getMaxBotBaseUrl(): string {
  const url = import.meta.env.VITE_MAX_BOT_URL?.trim();
  if (!url) return "";
  return url.split("?")[0]?.replace(/\/$/, "") ?? "";
}

/** Deeplink на бота / миниапп MAX: https://max.ru/<bot>?startapp=<payload> */
export function buildMaxDeepLink(startapp: string): string {
  const base = getMaxBotBaseUrl();
  const payload = startapp.trim();
  if (!base) return payload ? `https://max.ru?startapp=${encodeURIComponent(payload)}` : "https://max.ru";
  if (!payload) return base;
  return `${base}?startapp=${encodeURIComponent(payload)}`;
}

/** Ссылка на бота без параметров (fallback). */
export function getMaxBotUrl(): string {
  const base = getMaxBotBaseUrl();
  return base || "https://max.ru";
}

export const MAX_BIND_ERROR_KEY = "glosix-max-bind-error";
export const MAX_LOGIN_ERROR_KEY = "glosix-max-login-error";

export function setMaxBindError(message: string): void {
  try {
    sessionStorage.setItem(MAX_BIND_ERROR_KEY, message);
  } catch {
    /* ignore */
  }
}

export function takeMaxBindError(): string | null {
  try {
    const msg = sessionStorage.getItem(MAX_BIND_ERROR_KEY);
    if (msg) sessionStorage.removeItem(MAX_BIND_ERROR_KEY);
    return msg;
  } catch {
    return null;
  }
}

export function setMaxLoginError(message: string): void {
  try {
    sessionStorage.setItem(MAX_LOGIN_ERROR_KEY, message);
  } catch {
    /* ignore */
  }
}

export function takeMaxLoginError(): string | null {
  try {
    const msg = sessionStorage.getItem(MAX_LOGIN_ERROR_KEY);
    if (msg) sessionStorage.removeItem(MAX_LOGIN_ERROR_KEY);
    return msg;
  } catch {
    return null;
  }
}
