import { useMemo } from "react";
import { useRotatingTypewriterStatus } from "../hooks/useRotatingTypewriterStatus";
import { t } from "../i18n";

type Props = {
  active: boolean;
  /** Статус из SSE (GigaChat text2image). */
  status?: string;
};

export function ImageGenStatusLine({ active, status }: Props) {
  const messages = useMemo(() => {
    const base = [
      t("imageGenStatus1"),
      t("imageGenStatus2"),
      t("imageGenStatus3"),
      t("imageGenStatus4"),
      t("imageGenStatus5"),
    ];
    const fromServer = status?.trim();
    if (!fromServer) return base;
    if (base.includes(fromServer)) return base;
    return [fromServer, ...base];
  }, [status]);

  const { text, isTyping, label } = useRotatingTypewriterStatus(messages, active, {
    holdMs: 4400,
    stopAtLast: true,
  });

  if (!active) return null;

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={label}>
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
