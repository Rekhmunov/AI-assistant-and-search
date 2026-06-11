import type { Source } from "../api/client";

const SOURCES_FOOTER_RE = /\n{1,2}Источники:\s*(?:\n\[\d+\][^\n]*)+\s*$/i;

/** Убирает текстовый блок «Источники:» — в UI источники показываются чипами и панелью. */
export function stripSourcesFooter(text: string): string {
  const body = (text || "").trim();
  if (!body) return "";
  return body.replace(SOURCES_FOOTER_RE, "").trimEnd();
}

export function displayAnswerText(text: string, sources?: Source[]): string {
  const normalized = text || "";
  if (!sources?.length) return normalized;
  return stripSourcesFooter(normalized);
}
