export type InlineTextPart =
  | { type: "text"; value: string }
  | { type: "link"; label: string; href: string };

const MARKDOWN_LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/gi;
const BARE_URL_RE = /https?:\/\/[^\s<>\[\]()]+/gi;
const BARE_DOMAIN_RE =
  /\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,}(?:\/[a-z0-9@._~:/?#\[\]!$&'()*+,;=%_-]*)?)/gi;
const TRAILING_PUNCT = new Set([".", ",", ";", ":", "!", "?", "]", "»", '"', "'"]);

function trimBareUrl(raw: string): { href: string; trailing: string } {
  let href = raw;
  let trailing = "";
  while (href.length > 1) {
    const last = href[href.length - 1];
    if (last === ")") {
      const opens = (href.match(/\(/g) ?? []).length;
      const closes = (href.match(/\)/g) ?? []).length;
      if (closes <= opens) break;
    }
    if (!TRAILING_PUNCT.has(last)) break;
    trailing = last + trailing;
    href = href.slice(0, -1);
  }
  return { href, trailing };
}

/** Split text into plain chunks and markdown [label](url) links. */
export function splitMarkdownLinks(text: string): InlineTextPart[] {
  if (!text) return [];

  const parts: InlineTextPart[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  MARKDOWN_LINK_RE.lastIndex = 0;

  while ((match = MARKDOWN_LINK_RE.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", value: text.slice(last, match.index) });
    }
    parts.push({ type: "link", label: match[1], href: match[2] });
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push({ type: "text", value: text.slice(last) });
  }

  if (!parts.length) {
    parts.push({ type: "text", value: text });
  }

  return parts;
}

/** Find bare https:// URLs in plain text. */
export function splitBareUrls(text: string): InlineTextPart[] {
  if (!text) return [];

  const parts: InlineTextPart[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  BARE_URL_RE.lastIndex = 0;

  while ((match = BARE_URL_RE.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", value: text.slice(last, match.index) });
    }
    const { href, trailing } = trimBareUrl(match[0]);
    if (href) {
      parts.push({ type: "link", label: href, href });
    }
    if (trailing) {
      parts.push({ type: "text", value: trailing });
    }
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push({ type: "text", value: text.slice(last) });
  }

  if (!parts.length) {
    parts.push({ type: "text", value: text });
  }

  return parts;
}

/** Domain/path without scheme: max.ru/bot */
export function splitBareDomains(text: string): InlineTextPart[] {
  if (!text) return [];

  const parts: InlineTextPart[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  BARE_DOMAIN_RE.lastIndex = 0;

  while ((match = BARE_DOMAIN_RE.exec(text)) !== null) {
    if (match.index > last) {
      parts.push({ type: "text", value: text.slice(last, match.index) });
    }
    const raw = match[1];
    const { href, trailing } = trimBareUrl(raw);
    if (href) {
      parts.push({ type: "link", label: href, href });
    }
    if (trailing) {
      parts.push({ type: "text", value: trailing });
    }
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    parts.push({ type: "text", value: text.slice(last) });
  }

  if (!parts.length) {
    parts.push({ type: "text", value: text });
  }

  return parts;
}

function linkifyTextChunk(text: string): InlineTextPart[] {
  const withUrls = splitBareUrls(text);
  const out: InlineTextPart[] = [];
  for (const part of withUrls) {
    if (part.type === "link") {
      out.push(part);
      continue;
    }
    out.push(...splitBareDomains(part.value));
  }
  return out;
}

/** Markdown links first, then bare URLs and domain/path inside remaining text. */
export function linkifyPlainText(text: string): InlineTextPart[] {
  const withMd = splitMarkdownLinks(text);
  const out: InlineTextPart[] = [];

  for (const part of withMd) {
    if (part.type === "link") {
      out.push(part);
      continue;
    }
    out.push(...linkifyTextChunk(part.value));
  }

  return out;
}
