import type { ReactNode } from "react";
import { SourceLink } from "../components/SourceLink";
import { formatMarkdownText } from "./formatMarkdownText";
import { linkifyPlainText } from "./linkifyInlineText";
import { normalizeLinkHref } from "./sourceView";

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
        <SourceLink
          key={`${keyPrefix}-a-${keyCounter.n++}`}
          href={safe}
          className="answer-link cite-link"
        >
          {part.label}
        </SourceLink>,
      );
      continue;
    }
    const formatted = formatMarkdownText(part.value).replace(/\[\d+\]/g, "");
    if (formatted) {
      nodes.push(<span key={`${keyPrefix}-t-${keyCounter.n++}`}>{formatted}</span>);
    }
  }

  return nodes;
}

/** Inline answer text: links, inline `code`, citation markers stripped from body. */
export function renderInlineContent(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const inlineRe = /`([^`\n]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  const keyCounter = { n: 0 };

  while ((match = inlineRe.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(...renderLinkifiedPlain(text.slice(last, match.index), keyPrefix, keyCounter));
    }
    nodes.push(
      <code key={`${keyPrefix}-ic-${keyCounter.n++}`} className="answer-inline-code">
        {match[1]}
      </code>,
    );
    last = match.index + match[0].length;
  }

  if (last < text.length) {
    nodes.push(...renderLinkifiedPlain(text.slice(last), keyPrefix, keyCounter));
  }

  if (!nodes.length && text.trim()) {
    nodes.push(...renderLinkifiedPlain(text, keyPrefix, keyCounter));
  }

  return nodes;
}
