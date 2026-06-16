/** Пути и параметры, которые не должны попадать в поисковый индекс. */

export const PRIVATE_ROUTE_PREFIXES = [
  "/thread",
  "/history",
  "/profile",
  "/login",
  "/source-view",
  "/agents",
] as const;

// Включаем ?q= на /thread — это поисковый запрос, не нужен в индексе
const PRIVATE_QUERY_KEYS = ["WebAppStartParam", "etext", "startapp"] as const;
const PRIVATE_QUERY_RE = /(?:^|&)(?:WebAppStartParam|etext|startapp)(?:=|&|$)/i;

export function isPrivateAppPath(pathname: string): boolean {
  return PRIVATE_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function hasPrivateQueryParams(search: string): boolean {
  const q = search.startsWith("?") ? search.slice(1) : search;
  if (!q) return false;
  return PRIVATE_QUERY_RE.test(q);
}

export function shouldNoindexPage(pathname: string, search = "", hash = ""): boolean {
  if (isPrivateAppPath(pathname)) return true;
  if (hasPrivateQueryParams(search)) return true;
  if (/(?:^|[&#])(?:WebAppData|WebAppPlatform|WebAppVersion)=/i.test(`${search}${hash}`)) {
    return true;
  }
  return false;
}

/** Убирает трекинг-параметры MAX/рекламы из адресной строки после чтения. */
export function stripPrivateQueryParamsFromUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  let changed = false;
  for (const key of PRIVATE_QUERY_KEYS) {
    if (!url.searchParams.has(key)) continue;
    url.searchParams.delete(key);
    changed = true;
  }
  if (!changed) return;
  const search = url.searchParams.toString();
  const next = `${url.pathname}${search ? `?${search}` : ""}${url.hash}`;
  window.history.replaceState(window.history.state, "", next);
}
