import { useTypewriterText } from "../hooks/useTypewriterText";
import { t } from "../i18n";

export type SearchPhase = "routing" | "searching" | "answering" | "idle";

type Props = {
  phase: SearchPhase;
  needsSearch?: boolean;
};

function statusLabel(phase: SearchPhase, needsSearch?: boolean): string {
  if (phase === "routing") return t("thinking");
  if (phase === "searching") {
    return needsSearch ? t("searchingWeb") : t("searchingSolution");
  }
  if (phase === "answering") return t("composingAnswer");
  return t("searchingSolution");
}

export function SearchStatusLine({ phase, needsSearch }: Props) {
  const active = phase !== "idle";
  const label = statusLabel(phase, needsSearch);
  const { text, isTyping } = useTypewriterText(label, active);

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
