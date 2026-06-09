import type { MarkdownDocumentInfo } from "../api/client";
import { normalizeAnswerText } from "./answerText";
import { groupAnswerSegments } from "./groupAnswerSegments";
import { parseAnswerSegments } from "./parseAnswerSegments";

export type UnifiedDocument = {
  intro: string;
  markdownParts: string[];
  charts: string[];
  title?: string;
};

function isChartLang(lang?: string): boolean {
  return lang?.trim().toLowerCase() === "chart";
}

function isMarkdownLang(lang?: string): boolean {
  const l = lang?.trim().toLowerCase();
  return l === "markdown" || l === "md";
}

/**
 * Собирает единый документ из markdown в ответе, вложения markdown_document и chart-блоков.
 */
export function resolveUnifiedDocument(
  answer: unknown,
  markdownDocument?: MarkdownDocumentInfo | null,
): UnifiedDocument | null {
  const text = normalizeAnswerText(answer);
  const segments = groupAnswerSegments(parseAnswerSegments(text));

  const introParts: string[] = [];
  let documentFromAnswer: UnifiedDocument | null = null;
  const orphanCharts: string[] = [];
  const orphanMarkdown: string[] = [];

  for (const seg of segments) {
    if (seg.type === "text") {
      const trimmed = seg.content.trim();
      if (trimmed) introParts.push(trimmed);
      continue;
    }

    if (seg.type === "document") {
      documentFromAnswer = {
        intro: "",
        markdownParts: seg.markdownParts,
        charts: seg.charts,
      };
      continue;
    }

    if (seg.type === "code" && seg.content.trim()) {
      if (isChartLang(seg.lang)) orphanCharts.push(seg.content);
      else if (isMarkdownLang(seg.lang)) orphanMarkdown.push(seg.content);
    }
  }

  if (documentFromAnswer) {
    const mdParts = [...documentFromAnswer.markdownParts];
    if (markdownDocument?.content) {
      const attachment = markdownDocument.content.trim();
      if (attachment && !mdParts.some((p) => p.trim() === attachment)) {
        mdParts.unshift(attachment);
      }
    }
    return {
      intro: introParts.join("\n\n"),
      markdownParts: mdParts,
      charts: documentFromAnswer.charts,
      title: markdownDocument?.title,
    };
  }

  if (markdownDocument?.content && orphanCharts.length > 0) {
    return {
      intro: introParts.join("\n\n"),
      markdownParts: [markdownDocument.content, ...orphanMarkdown],
      charts: orphanCharts,
      title: markdownDocument.title,
    };
  }

  if (orphanMarkdown.length > 0 && orphanCharts.length > 0) {
    return {
      intro: introParts.join("\n\n"),
      markdownParts: orphanMarkdown,
      charts: orphanCharts,
    };
  }

  return null;
}
