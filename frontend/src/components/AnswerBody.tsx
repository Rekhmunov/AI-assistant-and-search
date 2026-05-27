import { useEffect, type ReactNode } from "react";
import type { Source } from "../api/client";
import { useStreamingReveal } from "../hooks/useStreamingReveal";
import { moveCitationsToParagraphEnds } from "../lib/moveCitationsToParagraphEnds";
import { parseAnswerSegments } from "../lib/parseAnswerSegments";
import { renderAnswerTextSegment } from "../lib/renderAnswerText";
import { CodeBlock } from "./CodeBlock";

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
  const displayText = revealActive ? rawText : moveCitationsToParagraphEnds(text);
  const segments = parseAnswerSegments(displayText, { expandUnfenced: !revealActive });
  const children: ReactNode[] = [];

  segments.forEach((seg, i) => {
    if (seg.type === "code") {
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
