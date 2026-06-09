import { isDocxExportableBlock } from "../lib/isDocxExportableBlock";
import { ChartCodeBlock } from "./ChartCodeBlock";
import { CollapsibleMarkdownDocument } from "./CollapsibleMarkdownDocument";
import { BlockToolbarActions } from "./BlockToolbarActions";

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

  const titleHint =
    code
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l.length >= 8) || label;
  const showDocxExport = isDocxExportableBlock(code, lang, partial);

  return (
    <div className={`answer-code-block${partial ? " answer-code-block--partial" : ""}`}>
      <div className="answer-code-header">
        <span className="answer-code-lang">{label}</span>
        <BlockToolbarActions
          className="answer-code-actions"
          copyText={code}
          docx={showDocxExport ? { content: code, titleHint } : null}
        />
      </div>
      <pre className="answer-code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
