const TWO_PART_TLDS = new Set([
  "co.uk",
  "com.au",
  "com.br",
  "co.jp",
  "com.ru",
  "org.ru",
  "net.ru",
  "co.nz",
]);

/** Домен для чипа: без www и без зоны (.ru, .com …). */
export function sourceDomainLabel(domainOrUrl: string): string {
  let host = domainOrUrl.trim().toLowerCase();
  if (!host) return "";

  if (host.includes("://")) {
    try {
      host = new URL(host).hostname.toLowerCase();
    } catch {
      /* keep raw */
    }
  }

  host = host.replace(/^www\./, "").split(":")[0];
  const parts = host.split(".").filter(Boolean);
  if (parts.length === 0) return host;
  if (parts.length === 1) return parts[0];

  const lastTwo = parts.slice(-2).join(".");
  if (parts.length >= 3 && TWO_PART_TLDS.has(lastTwo)) {
    return parts[parts.length - 3];
  }

  return parts[parts.length - 2];
}

export function sourceFaviconDomain(domainOrUrl: string): string {
  let host = domainOrUrl.trim().toLowerCase();
  if (host.includes("://")) {
    try {
      host = new URL(host).hostname.toLowerCase();
    } catch {
      return host;
    }
  }
  return host.replace(/^www\./, "").split(":")[0];
}

export function faviconUrl(domainOrUrl: string): string {
  const domain = sourceFaviconDomain(domainOrUrl);
  if (!domain) return "";
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=32`;
}
