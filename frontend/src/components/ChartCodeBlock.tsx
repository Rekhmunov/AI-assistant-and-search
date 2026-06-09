import { parseChartSpec } from "../lib/parseChartSpec";
import { AnswerChart } from "./AnswerChart";
import { CopyIconButton } from "./CopyIconButton";

type Props = {
  code: string;
  partial?: boolean;
};

export function ChartCodeBlock({ code, partial }: Props) {
  const spec = partial ? null : parseChartSpec(code);

  if (!partial && spec) {
    return <AnswerChart spec={spec} />;
  }

  return (
    <div className={`answer-code-block answer-chart-fallback${partial ? " answer-code-block--partial" : ""}`}>
      <div className="answer-code-header">
        <span className="answer-code-lang">chart</span>
        <div className="answer-code-actions">
          <CopyIconButton text={code} />
        </div>
      </div>
      {partial ? (
        <p className="answer-chart-loading muted-text">Строим график…</p>
      ) : (
        <>
          <p className="answer-chart-error muted-text">Не удалось построить график — проверьте JSON в блоке chart.</p>
          <pre className="answer-code-pre">
            <code>{code}</code>
          </pre>
        </>
      )}
    </div>
  );
}
