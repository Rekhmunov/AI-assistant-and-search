import { useMemo } from "react";
import { useRotatingTypewriterStatus } from "../hooks/useRotatingTypewriterStatus";
import { t } from "../i18n";

type Props = {
  active: boolean;
};

export function ImageGenStatusLine({ active }: Props) {
  const messages = useMemo(
    () => [
      t("imageGenStatus1"),
      t("imageGenStatus2"),
      t("imageGenStatus3"),
      t("imageGenStatus4"),
      t("imageGenStatus5"),
    ],
    [],
  );

  const { text, isTyping, label } = useRotatingTypewriterStatus(messages, active, {
    holdMs: 4400,
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
