import { useEffect, type ReactNode } from "react";
import type { Source } from "../api/client";
import { useStreamingReveal } from "../hooks/useStreamingReveal";
import { groupAnswerSegments } from "../lib/groupAnswerSegments";
import { parseAnswerSegments } from "../lib/parseAnswerSegments";
import { renderAnswerTextSegment } from "../lib/renderAnswerText";
import { CodeBlock } from "./CodeBlock";
import { DocumentAnswerBlock } from "./DocumentAnswerBlock";

type Props = {
  text: string;
  sources?: Source[];
  /** Плавное появление текста во время SSE-стрима */
  isStreaming?: boolean;
  /** false — когда догоняющая печать закончилась (можно синхронизировать тред с API) */
  onTypingChange?: (typing: boolean) => void;
};

export function AnswerBody({
  text,
  sources = [],
  isStreaming = false,
  onTypingChange,
}: Props) {
  const { text: revealed, isTyping } = useStreamingReveal(text, isStreaming);

  useEffect(() => {
    onTypingChange?.(isTyping);
  }, [isTyping, onTypingChange]);

  const revealActive = isStreaming || isTyping;
  const rawText = revealActive ? revealed : text;
  const segments = groupAnswerSegments(
    parseAnswerSegments(rawText, { expandUnfenced: !revealActive }),
  );
  const children: ReactNode[] = [];

  segments.forEach((seg, i) => {
    if (seg.type === "document") {
      children.push(
        <DocumentAnswerBlock
          key={`doc-${i}`}
          markdownParts={seg.markdownParts}
          charts={seg.charts}
          partial={seg.partial}
        />,
      );
      return;
    }

    if (seg.type === "code") {
      if (!seg.content.trim() && !(seg.partial && revealActive)) {
        return;
      }
      children.push(
        <CodeBlock
          key={`code-${i}`}
          code={seg.content}
          lang={seg.lang}
          partial={seg.partial}
        />,
      );
      return;
    }
    const trimmed = seg.content.trim();
    if (!trimmed) return;
    children.push(
      <div key={`text-${i}`} className="answer-text">
        {renderAnswerTextSegment(seg.content, sources, `t-${i}`)}
      </div>,
    );
  });

  return (
    <div className={`answer${revealActive ? " answer--streaming" : ""}`}>
      {children}
    </div>
  );
}
