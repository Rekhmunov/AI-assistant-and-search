import { isDocxExportableBlock } from "../lib/isDocxExportableBlock";
import { CopyIconButton } from "./CopyIconButton";
import { DocxExportIconButton } from "./DocxExportIconButton";

type Props = {
  code: string;
  lang?: string;
  partial?: boolean;
};

export function CodeBlock({ code, lang, partial }: Props) {
  const label = lang?.trim() || "code";
  const showDocx = isDocxExportableBlock(code, lang, partial);
  const titleHint = code.split("\n").map((l) => l.trim()).find((l) => l.length >= 8);

  return (
    <div className={`answer-code-block${partial ? " answer-code-block--partial" : ""}`}>
      <div className="answer-code-header">
        <span className="answer-code-lang">{label}</span>
        <div className="answer-code-actions">
          <CopyIconButton text={code} />
          {showDocx ? (
            <DocxExportIconButton content={code} titleHint={titleHint} />
          ) : null}
        </div>
      </div>
      <pre className="answer-code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
