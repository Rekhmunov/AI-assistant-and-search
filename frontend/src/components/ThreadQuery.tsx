import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";
import { useDesktopLayout } from "../hooks/useDesktopLayout";

type Props = {
  query: string;
};

export function ThreadQuery({ query }: Props) {
  const isDesktop = useDesktopLayout();
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [menuOpen]);

  const copyQuery = async () => {
    if (!query.trim()) return;
    try {
      await navigator.clipboard.writeText(query);
      setCopied(true);
      window.setTimeout(() => {
        setCopied(false);
        setMenuOpen(false);
      }, 1500);
    } catch {
      /* ignore */
    }
  };

  if (isDesktop) {
    return (
      <div className="thread-query">
        <p className="thread-query-text">{query}</p>
      </div>
    );
  }

  return (
    <div
      ref={rootRef}
      className={`thread-query thread-query--mobile${menuOpen ? " thread-query--menu-open" : ""}`}
    >
      <button
        type="button"
        className="thread-query-trigger"
        onClick={() => setMenuOpen((open) => !open)}
        aria-expanded={menuOpen}
        aria-haspopup="true"
        aria-label={t("queryLabel")}
      >
        <span className="thread-query-text">{query}</span>
      </button>

      {menuOpen && (
        <div className="thread-query-menu" role="menu">
          <button
            type="button"
            className="answer-icon-btn thread-query-copy-btn"
            role="menuitem"
            onClick={() => void copyQuery()}
            aria-label={copied ? t("copied") : t("copyQuery")}
            title={copied ? t("copied") : t("copyQuery")}
          >
            <CopyIcon />
          </button>
        </div>
      )}
    </div>
  );
}

function CopyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
