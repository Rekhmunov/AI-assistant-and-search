import type { Source } from "../api/client";
import { formatAnswerForDisplay } from "../lib/formatAnswer";
import { renderTextWithCitations } from "../lib/parseCitations";

type Props = {
  text: string;
  sources?: Source[];
};

export function AnswerBody({ text, sources = [] }: Props) {
  const display = formatAnswerForDisplay(text);
  const content =
    sources.length > 0 ? renderTextWithCitations(display, sources) : display;

  return <div className="answer">{content}</div>;
}
