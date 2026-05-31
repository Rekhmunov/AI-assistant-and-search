/** Safe http(s) URL for in-app source viewer. */
export function parseSourceViewUrl(raw: string | null): string | null {
  if (!raw?.trim()) return null;
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.href;
  } catch {
    return null;
  }
}

export function buildSourceViewPath(url: string): string {
  return `/source-view?url=${encodeURIComponent(url)}`;
}
