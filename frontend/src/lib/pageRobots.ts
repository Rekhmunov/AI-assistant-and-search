/** Пути и параметры, которые не должны попадать в поисковый индекс. */

export const PRIVATE_ROUTE_PREFIXES = [
  "/thread",
  "/history",
  "/profile",
  "/login",
  "/source-view",
] as const;

const PRIVATE_QUERY_RE = /(?:^|&)(?:WebAppStartParam|etext|startapp)=/i;

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
