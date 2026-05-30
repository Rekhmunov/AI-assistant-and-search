import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { Source } from "../api/client";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { sourceDomainLabel, faviconUrl } from "../lib/sourceDomainLabel";
import { t } from "../i18n";

type Props = {
  open: boolean;
  query?: string;
  sources: Source[];
  onClose: () => void;
};

export function SourcesPanel({ open, query, sources, onClose }: Props) {
  useBodyScrollLock(open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const title = query?.trim()
    ? t("sourcesForQuery", { query: query.trim() })
    : t("sources");

  return createPortal(
    <div className="sources-panel-overlay app-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="sources-panel app-modal app-modal--wide"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sources-panel-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sources-panel-header">
          <h2 id="sources-panel-title" className="sources-panel-title">
            {title}
          </h2>
          <button type="button" className="sources-panel-close" onClick={onClose} aria-label={t("close")}>
            ×
          </button>
        </div>

        <ul className="sources-panel-list">
          {sources.map((source) => (
            <li key={source.index}>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="sources-panel-item"
                id={`source-${source.index}`}
              >
                <div className="sources-panel-item-head">
                  <img
                    className="sources-panel-favicon"
                    src={faviconUrl(source.domain || source.url)}
                    alt=""
                    width={18}
                    height={18}
                    loading="lazy"
                    decoding="async"
                  />
                  <span className="sources-panel-domain">
                    {sourceDomainLabel(source.domain || source.url)}
                  </span>
                </div>
                <span className="sources-panel-item-title">{source.title || source.url}</span>
                {source.snippet?.trim() && (
                  <p className="sources-panel-snippet">{source.snippet.trim()}</p>
                )}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
