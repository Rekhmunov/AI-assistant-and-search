import { useMemo } from "react";
import { useRotatingTypewriterStatus } from "../hooks/useRotatingTypewriterStatus";
import { t } from "../i18n";

type Props = {
  active: boolean;
  /** Статус из SSE (дополняет ротацию на сервере). */
  status?: string;
};

export function DocGenStatusLine({ active, status }: Props) {
  const messages = useMemo(() => {
    const base = [
      t("docGenStatus1"),
      t("docGenStatus2"),
      t("docGenStatus3"),
      t("docGenStatus4"),
      t("docGenStatus5"),
      t("docGenStatus6"),
      t("docGenStatus7"),
    ];
    const fromServer = status?.trim();
    if (!fromServer) return base;
    if (base.includes(fromServer)) return base;
    return [fromServer, ...base];
  }, [status]);

  const { text, isTyping, label } = useRotatingTypewriterStatus(messages, active, {
    holdMs: 2600,
  });

  if (!active) return null;

  return (
    <div className="search-status doc-gen-status-line" role="status" aria-live="polite" aria-label={label}>
      <span className="search-status-dot" />
      <span
        className={`search-status-text${isTyping ? " search-status-text--typing" : ""}`}
        aria-hidden={isTyping}
      >
        {text}
      </span>
    </div>
  );
}
