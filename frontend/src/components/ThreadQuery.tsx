import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";
import { useDesktopLayout } from "../hooks/useDesktopLayout";

type Props = {
  query: string;
};

const LONG_PRESS_MS = 450;

export function ThreadQuery({ query }: Props) {
  const isDesktop = useDesktopLayout();
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);

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

  const clearLongPressTimer = () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

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

  const startLongPress = () => {
    longPressTriggeredRef.current = false;
    clearLongPressTimer();
    longPressTimerRef.current = window.setTimeout(() => {
      longPressTriggeredRef.current = true;
      setMenuOpen(true);
    }, LONG_PRESS_MS);
  };

  const endLongPress = () => {
    clearLongPressTimer();
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
      <div
        className="thread-query-trigger"
        role="button"
        tabIndex={0}
        aria-haspopup="true"
        aria-expanded={menuOpen}
        aria-label={t("queryLabel")}
        onPointerDown={startLongPress}
        onPointerUp={endLongPress}
        onPointerLeave={endLongPress}
        onPointerCancel={endLongPress}
        onContextMenu={(event) => {
          event.preventDefault();
          setMenuOpen(true);
        }}
      >
        <span className="thread-query-text">{query}</span>
      </div>

      {menuOpen && (
        <div className="thread-query-menu" role="menu">
          <button
            type="button"
            className="thread-query-copy-btn"
            role="menuitem"
            onClick={() => void copyQuery()}
          >
            {copied ? t("copied") : t("copyAnswer")}
          </button>
        </div>
      )}
    </div>
  );
}
