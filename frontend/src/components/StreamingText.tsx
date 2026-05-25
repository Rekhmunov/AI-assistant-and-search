import { formatAnswerForDisplay } from "../lib/formatAnswer";

export function StreamingText({ text }: { text: string; streaming?: boolean }) {
  const display = formatAnswerForDisplay(text);
  return <div className="answer">{display}</div>;
}
