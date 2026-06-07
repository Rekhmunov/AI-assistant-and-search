import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t } from "../i18n";

const DROPDOWN_ID = "composer-model-dropdown";

type Props = {
  plan: "free" | "pro";
  onOpenProModal: () => void;
  keepFocusOnPress?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export function ComposerModelSelector({
  plan,
  onOpenProModal,
  keepFocusOnPress = false,
  onOpenChange,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<{ top: number; left: number } | null>(null);

  const isPro = plan === "pro";
  const showLitePro = !isPro;

  const positionMenu = useCallback(() => {
    const btn = buttonRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const menuWidth = 248;
    const left = Math.min(Math.max(8, rect.right - menuWidth), window.innerWidth - menuWidth - 8);
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

  const setMenuOpen = useCallback(
    (next: boolean) => {
      onOpenChange?.(next);
      setOpen(next);
    },
    [onOpenChange],
  );

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("touchstart", onPointerDown, { passive: true });
      document.addEventListener("keydown", onKey);
    }, 250);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, setMenuOpen]);

  const handleProClick = () => {
    setMenuOpen(false);
    if (isPro) return;
    onOpenProModal();
  };

  const onTriggerClick = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setMenuOpen(!open);
  };

  const dropdown =
    open && menuStyle
      ? createPortal(
          <div
            ref={menuRef}
            id={DROPDOWN_ID}
            className="composer-model-dropdown composer-model-dropdown--portal"
            role="menu"
            style={{
              top: menuStyle.top,
              left: menuStyle.left,
              transform: "translateY(-100%)",
            }}
          >
            {showLitePro && (
              <ModelOption
                label={t("modelSelectorLite")}
                active
                onClick={() => setMenuOpen(false)}
              />
            )}
            {showLitePro ? (
              <ModelOption
                label={t("modelSelectorPro")}
                locked
                onClick={handleProClick}
              />
            ) : (
              <ModelOption
                label={t("modelSelectorPro")}
                active
                onClick={() => setMenuOpen(false)}
              />
            )}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="composer-model-selector" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="composer-model-trigger"
        aria-label={t("modelSelectorLabel")}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={DROPDOWN_ID}
        onPointerDown={keepFocusOnPress ? (e) => e.preventDefault() : undefined}
        onClick={onTriggerClick}
      >
        <span className="composer-model-trigger-label">{t("modelSelectorLabel")}</span>
        <ChevronIcon />
      </button>
      {dropdown}
    </div>
  );
}

function ModelOption({
  label,
  active = false,
  locked = false,
  onClick,
}: {
  label: string;
  active?: boolean;
  locked?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`composer-model-option${active ? " composer-model-option--active" : ""}${locked ? " composer-model-option--locked" : ""}`}
      role="menuitem"
      onPointerDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <span className="composer-model-option-label">{label}</span>
      {locked ? <LockIcon /> : active ? <CheckIcon /> : null}
    </button>
  );
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden className="composer-model-lock">
      <path
        d="M7 11V8a5 5 0 0110 0v3M6 11h12v9H6V11z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden className="composer-model-check">
      <path
        d="M5 12l4 4L19 7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
