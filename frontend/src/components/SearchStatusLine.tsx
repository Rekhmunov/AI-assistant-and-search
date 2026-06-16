import { useEffect, useRef, useState } from "react";
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
  customStatus?: string | null;
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

/** Тикер доменов: показывает по одному с плавной анимацией */
function DomainTicker({ domains }: { domains: string[] }) {
  const [idx, setIdx] = useState(0);
  const [visible, setVisible] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!domains.length) return;
    setIdx(0);
    setVisible(true);

    const cycle = (current: number) => {
      const next = current + 1;
      if (next >= domains.length) return; // все домены показаны — ждём конца поиска

      // Плавно скрываем текущий
      setVisible(false);
      timerRef.current = setTimeout(() => {
        setIdx(next);
        setVisible(true);
        timerRef.current = setTimeout(() => cycle(next), 2500);
      }, 400); // 400мс на fade-out, потом следующий
    };

    timerRef.current = setTimeout(() => cycle(0), 2500);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [domains]);

  if (!domains.length) return null;

  const domain = domains[idx] ?? domains[0];

  return (
    <span
      className={`search-status-site-ticker${visible ? " search-status-site-ticker--visible" : ""}`}
      aria-hidden
    >
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
  );
}

export function SearchStatusLine({ phase, needsSearch, customStatus, searchSiteDomains }: Props) {
  const active = phase !== "idle";
  const label = statusLabel(phase, needsSearch, customStatus);
  const showTicker = phase === "searching" && needsSearch && searchSiteDomains && searchSiteDomains.length > 0;

  if (!active) return null;

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={label}>
      <span className="search-status-dot" />
      <span className="search-status-body">
        <span className="search-status-text">
          {label}{showTicker ? ":" : ""}
        </span>
        {showTicker && <DomainTicker domains={searchSiteDomains!} />}
      </span>
    </div>
  );
}
