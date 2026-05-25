import { t } from "../i18n";

export type SearchPhase = "routing" | "searching" | "answering" | "idle";

type Props = {
  phase: SearchPhase;
  needsSearch?: boolean;
};

export function SearchStatusLine({ phase, needsSearch }: Props) {
  if (phase === "idle") return null;

  let label = t("searchingSolution");
  if (phase === "routing") {
    label = t("thinking");
  } else if (phase === "searching") {
    label = needsSearch ? t("searchingWeb") : t("searchingSolution");
  } else if (phase === "answering") {
    label = t("composingAnswer");
  }

  return (
    <div className="search-status" role="status" aria-live="polite">
      <span className="search-status-dot" />
      <span className="search-status-text">{label}</span>
    </div>
  );
}
