import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "../i18n";

const DROPDOWN_ID = "composer-attach-dropdown";

type Props = {
  disabled?: boolean;
  /** Веб: сразу открыть системный выбор файлов */
  directPick?: boolean;
  onDirectPick?: () => void;
  /** Мобильная / миниапп: подменю */
  onPickGallery?: () => void;
  onPickCamera?: () => void;
  onPickFiles?: () => void;
};

export function ComposerAttachMenu({
  disabled,
  directPick = false,
  onDirectPick,
  onPickGallery,
  onPickCamera,
  onPickFiles,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<{ top: number; left: number } | null>(null);

  const positionMenu = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const menuWidth = 220;
    const left = Math.min(
      Math.max(8, rect.left),
      window.innerWidth - menuWidth - 8,
    );
    setMenuStyle({ top: rect.top - 8, left });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setMenuStyle(null);
      return;
    }
    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [open, positionMenu]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("touchstart", onPointerDown, { passive: true });
      document.addEventListener("keydown", onKey);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (fn: () => void) => {
    setOpen(false);
    fn();
  };

  const onAttachClick = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled) return;

    if (directPick) {
      onDirectPick?.();
      return;
    }

    setOpen((v) => !v);
  };

  const dropdown =
    open && menuStyle && !directPick
      ? createPortal(
          <div
            ref={menuRef}
            id={DROPDOWN_ID}
            className="composer-attach-dropdown composer-attach-dropdown--portal"
            role="menu"
            style={{
              top: menuStyle.top,
              left: menuStyle.left,
              transform: "translateY(-100%)",
            }}
          >
            <button type="button" role="menuitem" onClick={() => choose(() => onPickGallery?.())}>
              <ImageMenuIcon />
              <span>{t("attachGallery")}</span>
            </button>
            <button type="button" role="menuitem" onClick={() => choose(() => onPickCamera?.())}>
              <CameraMenuIcon />
              <span>{t("attachCamera")}</span>
            </button>
            <button type="button" role="menuitem" onClick={() => choose(() => onPickFiles?.())}>
              <DocMenuIcon />
              <span>{t("attachChooseFiles")}</span>
            </button>
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="composer-attach-menu" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="composer-icon composer-icon--attach"
        aria-label={directPick ? t("attachUploadAll") : t("attachAdd")}
        aria-expanded={directPick ? undefined : open}
        aria-haspopup={directPick ? undefined : "menu"}
        aria-controls={directPick ? undefined : DROPDOWN_ID}
        disabled={disabled}
        onClick={onAttachClick}
      >
        <PlusIcon />
      </button>
      {dropdown}
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function DocMenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M14 2v6h6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function ImageMenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="8.5" cy="10" r="1.5" fill="currentColor" />
      <path d="M3 16l5-5 4 4 3-3 6 6" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function CameraMenuIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 8h4l2-2h4l2 2h4v10H4V8z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="13" r="3" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}
