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

/** Один домен за раз, плавная смена каждые 2 секунды */
function DomainTicker({ domains, active }: { domains: string[]; active: boolean }) {
  const [idx, setIdx] = useState(0);
  const [show, setShow] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clear = () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };

  useEffect(() => {
    if (!active || !domains.length) {
      setShow(false);
      return;
    }
    setIdx(0);
    setShow(false); // ждём загрузки фавикона перед показом

    return () => clear();
  }, [domains, active]); // eslint-disable-line react-hooks/exhaustive-deps

  // Запускаем цикл только когда фавикон загружен (вызывается из onFaviconLoad/onFaviconError)
  const startCycle = (i: number) => {
    setShow(true);
    clear();

    const next = i + 1;
    if (next >= domains.length) return;

    timer.current = setTimeout(() => {
      setShow(false);
      timer.current = setTimeout(() => {
        setIdx(next);
      }, 400);
    }, 2000);
  };

  const onFaviconLoad = () => {
    startCycle(idx);
  };

  const onFaviconError = (e: React.SyntheticEvent<HTMLImageElement>) => {
    (e.target as HTMLImageElement).style.display = "none";
    startCycle(idx);
  };

  if (!active || !domains.length) return null;

  const domain = domains[idx] ?? "";
  if (!domain) return null;

  return (
    <span
      className={`search-status-ticker${show ? " search-status-ticker--show" : ""}`}
      aria-hidden
    >
      <img
        key={domain}
        className="search-status-favicon"
        src={faviconUrl(domain)}
        alt=""
        width={12}
        height={12}
        decoding="async"
        onLoad={onFaviconLoad}
        onError={onFaviconError}
      />
      <span className="search-status-domain">{domain}</span>
    </span>
  );
}

export function SearchStatusLine({ phase, needsSearch, customStatus, searchSiteDomains }: Props) {
  const active = phase !== "idle";
  const label = statusLabel(phase, needsSearch, customStatus);
  const showTicker = phase === "searching" && needsSearch && !!searchSiteDomains?.length;

  if (!active) return null;

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={label}>
      <span className="search-status-dot" />
      <span className="search-status-body">
        <span className="search-status-text">
          {label}{showTicker ? ":" : ""}
        </span>
        {showTicker && (
          <DomainTicker domains={searchSiteDomains!} active={showTicker} />
        )}
      </span>
    </div>
  );
}
