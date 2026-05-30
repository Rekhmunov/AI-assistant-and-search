import type { ReactNode } from "react";
import type { Source } from "../api/client";

/** Убирает оставшиеся [N] из текста — чипы рендерятся отдельно. */
export function renderTextWithCitations(text: string, _sources: Source[]): ReactNode[] {
  if (!text) return [];
  return [text.replace(/\[\d+\]/g, "")];
}
