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

export type IframeEmbedState = "ready" | "blocked";

type IframeLike = Pick<HTMLIFrameElement, "contentDocument" | "contentWindow">;

/** Best-effort check whether an iframe loaded embeddable content. */
export function detectIframeEmbedState(iframe: IframeLike): IframeEmbedState {
  try {
    const doc = iframe.contentDocument ?? iframe.contentWindow?.document ?? null;
    if (!doc) return "blocked";

    const href = doc.defaultView?.location?.href ?? "";
    if (!href || href === "about:blank") return "blocked";

    const bodyHtml = doc.body?.innerHTML?.trim() ?? "";
    const bodyText = doc.body?.innerText?.trim() ?? "";
    if (!bodyHtml && !bodyText) return "blocked";

    return "ready";
  } catch {
    // Cross-origin access is blocked when a real page loaded in the iframe.
    return "ready";
  }
}

export const SOURCE_VIEW_EMBED_HINT_DELAY_MS = 2500;
