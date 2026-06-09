import { ChartCodeBlock } from "./ChartCodeBlock";
import { CollapsibleMarkdownDocument } from "./CollapsibleMarkdownDocument";
import { CopyIconButton } from "./CopyIconButton";

type Props = {
  code: string;
  lang?: string;
  partial?: boolean;
};

export function CodeBlock({ code, lang, partial }: Props) {
  const label = lang?.trim() || "code";
  const isMarkdown = label === "markdown" || label === "md";
  const isChart = label === "chart";

  if (isChart) {
    return <ChartCodeBlock code={code} partial={partial} />;
  }

  if (isMarkdown && !partial) {
    const title =
      code
        .split("\n")
        .map((l) => l.trim())
        .find((l) => l.startsWith("#"))?.replace(/^#+\s*/, "") ||
      code.split("\n").map((l) => l.trim()).find((l) => l.length >= 8) ||
      "Документ";
    return <CollapsibleMarkdownDocument title={title} content={code} />;
  }

  return (
    <div className={`answer-code-block${partial ? " answer-code-block--partial" : ""}`}>
      <div className="answer-code-header">
        <span className="answer-code-lang">{label}</span>
        <div className="answer-code-actions">
          <CopyIconButton text={code} />
        </div>
      </div>
      <pre className="answer-code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
