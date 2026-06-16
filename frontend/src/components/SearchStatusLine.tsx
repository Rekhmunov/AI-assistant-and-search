import { useTypewriterText } from "../hooks/useTypewriterText";
import { t } from "../i18n";
import { faviconUrl } from "../lib/sourceDomainLabel";

export type SearchPhase =
  | "routing"
  | "searching"
  | "answering"
  | "image_generating"
  | "document_generating"
  | "preparing"
  | "idle";

type Props = {
  phase: SearchPhase;
  needsSearch?: boolean;
  /** Статус из SSE (GigaChat text2image): «Делаем шедевр…» */
  customStatus?: string | null;
  /** Домены из Yandex Search — показываем в статусе «Ищем в интернете» */
  searchSiteDomains?: string[];
};

function statusLabel(phase: SearchPhase, needsSearch?: boolean, customStatus?: string | null): string {
  if (customStatus?.trim()) return customStatus.trim();
  if (phase === "preparing") return t("answerPreparing");
  if (phase === "document_generating") return t("docGenPreparing");
  if (phase === "image_generating") return t("imageGenWorking");
  if (phase === "routing") return t("thinking");
  if (phase === "searching") {
    return needsSearch ? t("searchingWeb") : t("searchingSolution");
  }
  if (phase === "answering") return t("composingAnswer");
  return t("searchingSolution");
}

export function SearchStatusLine({ phase, needsSearch, customStatus, searchSiteDomains }: Props) {
  const active = phase !== "idle";
  const label = statusLabel(phase, needsSearch, customStatus);
  const { text, isTyping } = useTypewriterText(label, active);
  const showSites = phase === "searching" && needsSearch && searchSiteDomains && searchSiteDomains.length > 0;

  if (!active) return null;

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={label}>
      <span className="search-status-dot" />
      <span className="search-status-body">
        <span
          className={`search-status-text${isTyping ? " search-status-text--typing" : ""}`}
          aria-hidden={isTyping}
        >
          {text}{showSites ? ":" : ""}
        </span>
        {showSites && (
          <span className="search-status-sites" aria-hidden>
            {searchSiteDomains.slice(0, 5).map((domain) => (
              <span key={domain} className="search-status-site">
                <img
                  className="search-status-favicon"
                  src={faviconUrl(domain)}
                  alt=""
                  width={12}
                  height={12}
                  loading="lazy"
                  decoding="async"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <span className="search-status-domain">{domain}</span>
              </span>
            ))}
          </span>
        )}
      </span>
    </div>
  );
}
