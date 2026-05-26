import type { ReactNode } from "react";
import type { Source } from "../api/client";
import { parseAnswerSegments } from "../lib/parseAnswerSegments";
import { renderAnswerTextSegment } from "../lib/renderAnswerText";
import { CodeBlock } from "./CodeBlock";

type Props = {
  text: string;
  sources?: Source[];
};

export function AnswerBody({ text, sources = [] }: Props) {
  const segments = parseAnswerSegments(text);
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

  return <div className="answer">{children}</div>;
}
