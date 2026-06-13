import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Plus, FileText, Image, Camera } from "lucide-react";
import { t } from "../i18n";

const DROPDOWN_ID = "composer-attach-dropdown";

type Props = {
  disabled?: boolean;
  /** Веб: сразу открыть системный выбор файлов */
  directPick?: boolean;
  /** Не снимать фокус с textarea при тапе (mobile toolbar) */
  keepFocusOnPress?: boolean;
  onOpenChange?: (open: boolean) => void;
  onDirectPick?: () => void;
  /** Мобильная / миниапп: подменю */
  onPickGallery?: () => void;
  onPickCamera?: () => void;
  onPickFiles?: () => void;
};

export function ComposerAttachMenu({
  disabled,
  directPick = false,
  keepFocusOnPress = false,
  onOpenChange,
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
    onOpenChange?.(open);
  }, [open, onOpenChange]);

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
    }, 250);
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
            <button
              type="button"
              role="menuitem"
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => choose(() => onPickGallery?.())}
            >
              <ImageMenuIcon />
              <span>{t("attachGallery")}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => choose(() => onPickCamera?.())}
            >
              <CameraMenuIcon />
              <span>{t("attachCamera")}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => choose(() => onPickFiles?.())}
            >
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
        onPointerDown={keepFocusOnPress ? (e) => e.preventDefault() : undefined}
        onClick={onAttachClick}
      >
        <PlusIcon />
      </button>
      {dropdown}
    </div>
  );
}

function PlusIcon() {
  return <Plus width={22} height={22} strokeWidth={2} aria-hidden />;
}

function DocMenuIcon() {
  return <FileText width={18} height={18} strokeWidth={1.6} aria-hidden />;
}

function ImageMenuIcon() {
  return <Image width={18} height={18} strokeWidth={1.6} aria-hidden />;
}

function CameraMenuIcon() {
  return <Camera width={18} height={18} strokeWidth={1.6} aria-hidden />;
}
