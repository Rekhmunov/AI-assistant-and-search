import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";

type Props = {
  onDocx: () => void;
  disabled?: boolean;
  className?: string;
};

export function DownloadFormatMenu({ onDocx, disabled = false, className = "answer-icon-btn" }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const el = rootRef.current;
      if (!el || e.target instanceof Node && el.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown, { passive: true });
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
    };
  }, [open]);

  return (
    <div className="download-format-menu" ref={rootRef}>
      <button
        type="button"
        className={className}
        disabled={disabled}
        aria-label={t("downloadDocument")}
        title={t("downloadDocument")}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <DownloadIcon />
      </button>
      {open ? (
        <div className="download-format-menu-dropdown" role="menu">
          <button
            type="button"
            className="download-format-menu-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onDocx();
            }}
          >
            {t("downloadFormatDocx")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3v12m0 0l4-4m-4 4l-4-4M5 21h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
