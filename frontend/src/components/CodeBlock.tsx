import { CopyIconButton } from "./CopyIconButton";

type Props = {
  code: string;
  lang?: string;
  partial?: boolean;
};

export function CodeBlock({ code, lang, partial }: Props) {
  const label = lang?.trim() || "code";

  return (
    <div className={`answer-code-block${partial ? " answer-code-block--partial" : ""}`}>
      <div className="answer-code-header">
        <span className="answer-code-lang">{label}</span>
        <CopyIconButton text={code} />
      </div>
      <pre className="answer-code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
