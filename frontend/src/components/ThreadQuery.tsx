import { useEffect, useRef, useState } from "react";
import type { MessageAttachment } from "../api/client";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { t } from "../i18n";
import { stripUserQueryDisplay } from "../lib/userQueryDisplay";
import { ThreadQueryAttachments } from "./ThreadQueryAttachments";

type Props = {
  query: string;
  attachments?: MessageAttachment[];
};

const LONG_PRESS_MS = 450;

export function ThreadQuery({ query, attachments = [] }: Props) {
  const displayQuery = stripUserQueryDisplay(query);
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
    if (!displayQuery.trim()) return;
    try {
      await navigator.clipboard.writeText(displayQuery);
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

  const chips = attachments.length > 0 ? <ThreadQueryAttachments attachments={attachments} /> : null;

  if (isDesktop) {
    return (
      <div className="thread-query-block">
        <div className="thread-query">
          <p className="thread-query-text">{displayQuery}</p>
        </div>
        {chips}
      </div>
    );
  }

  return (
    <div className="thread-query-block thread-query-block--mobile">
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
        <span className="thread-query-text">{displayQuery}</span>
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
    {chips}
    </div>
  );
}
