import type { ReactNode } from "react";
import { SourceLink } from "../components/SourceLink";
import { linkifyPlainText } from "./linkifyInlineText";
import { normalizeLinkHref } from "./sourceView";

/**
 * Токенизирует строку inline-markdown на сегменты:
 * plain | bold | italic | md-link | inline-code
 */
type InlineToken =
  | { type: "plain"; text: string }
  | { type: "bold"; text: string }
  | { type: "italic"; text: string }
  | { type: "link"; label: string; href: string }
  | { type: "code"; text: string };

function tokenizeInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  // Порядок важен: code > bold > italic > md-link
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|(?<![*])\*(?![*])[^*\n]+\*(?![*])|_[^_\n]+_|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) tokens.push({ type: "plain", text: text.slice(last, m.index) });
    const raw = m[0];
    if (raw.startsWith("`")) {
      tokens.push({ type: "code", text: raw.slice(1, -1) });
    } else if (raw.startsWith("**") || raw.startsWith("__")) {
      tokens.push({ type: "bold", text: raw.slice(2, -2) });
    } else if (raw.startsWith("[")) {
      const lm = raw.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (lm) tokens.push({ type: "link", label: lm[1], href: lm[2] });
      else tokens.push({ type: "plain", text: raw });
    } else {
      // italic: *text* or _text_
      tokens.push({ type: "italic", text: raw.slice(1, -1) });
    }
    last = m.index + raw.length;
  }
  if (last < text.length) tokens.push({ type: "plain", text: text.slice(last) });
  return tokens;
}

function renderLinkifiedPlain(text: string, keyPrefix: string, keyCounter: { n: number }): ReactNode[] {
  const nodes: ReactNode[] = [];
  if (!text.trim()) return nodes;

  for (const part of linkifyPlainText(text)) {
    if (part.type === "link") {
      const safe = normalizeLinkHref(part.href);
      if (!safe) {
        nodes.push(<span key={`${keyPrefix}-t-${keyCounter.n++}`}>{part.label}</span>);
        continue;
      }
      nodes.push(
        <SourceLink key={`${keyPrefix}-a-${keyCounter.n++}`} href={safe} className="answer-link cite-link">
          {part.label}
        </SourceLink>,
      );
      continue;
    }
    // Remove citation markers [1], [2] from plain text
    const clean = part.value.replace(/\[\d+\]/g, "");
    if (clean.trim()) {
      nodes.push(<span key={`${keyPrefix}-t-${keyCounter.n++}`}>{clean}</span>);
    }
  }
  return nodes;
}

/** Inline answer text: bold, italic, links, inline code, plain text. */
export function renderInlineContent(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const keyCounter = { n: 0 };
  // Strip citation markers before tokenizing
  const clean = text.replace(/\[\d+\]/g, "");
  const tokens = tokenizeInline(clean);

  for (const tok of tokens) {
    const k = `${keyPrefix}-${keyCounter.n++}`;
    if (tok.type === "code") {
      nodes.push(<code key={k} className="answer-inline-code">{tok.text}</code>);
    } else if (tok.type === "bold") {
      nodes.push(<strong key={k} className="answer-bold">{tok.text}</strong>);
    } else if (tok.type === "italic") {
      nodes.push(<em key={k} className="answer-italic">{tok.text}</em>);
    } else if (tok.type === "link") {
      const safe = normalizeLinkHref(tok.href);
      if (safe) {
        nodes.push(
          <SourceLink key={k} href={safe} className="answer-link cite-link">
            {tok.label}
          </SourceLink>,
        );
      } else {
        nodes.push(<span key={k}>{tok.label}</span>);
      }
    } else {
      // plain — linkify URLs
      nodes.push(...renderLinkifiedPlain(tok.text, `${keyPrefix}-p-${keyCounter.n}`, keyCounter));
    }
  }

  if (!nodes.length && text.trim()) {
    nodes.push(...renderLinkifiedPlain(clean, keyPrefix, keyCounter));
  }

  return nodes;
}
