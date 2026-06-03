import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import { deleteThread, renameThread } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  threadId: string;
  title: string;
};

const MENU_WIDTH = 220;
const MENU_GAP = 6;

type MenuPlacement = {
  top: number;
  left: number;
  transform?: string;
};

function computeMenuPlacement(anchor: DOMRect, menuHeight: number): MenuPlacement {
  const left = Math.min(
    Math.max(8, anchor.right - MENU_WIDTH),
    window.innerWidth - MENU_WIDTH - 8,
  );
  const belowTop = anchor.bottom + MENU_GAP;
  const fitsBelow = belowTop + menuHeight <= window.innerHeight - 8;
  if (fitsBelow) {
    return { top: belowTop, left };
  }
  return { top: anchor.top - MENU_GAP, left, transform: "translateY(-100%)" };
}

export function ThreadHistoryMenu({ threadId, title }: Props) {
  const menuId = useId();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { id: activeThreadId } = useParams();
  const rootRef = useRef<HTMLDivElement>(null);
  const kebabRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [error, setError] = useState("");
  const [menuPlacement, setMenuPlacement] = useState<MenuPlacement | null>(null);

  useEffect(() => {
    setDraftTitle(title);
  }, [title]);

  const positionMenu = useCallback(() => {
    const btn = kebabRef.current;
    if (!btn) return;
    const rect = btn.getBoundingClientRect();
    const menuHeight = menuRef.current?.offsetHeight ?? (confirmDelete ? 120 : 100);
    setMenuPlacement(computeMenuPlacement(rect, menuHeight));
  }, [confirmDelete]);

  useLayoutEffect(() => {
    if (!menuOpen) {
      setMenuPlacement(null);
      return;
    }
    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [menuOpen, confirmDelete, positionMenu]);

  useEffect(() => {
    if (!menuOpen && !renaming) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setMenuOpen(false);
      setConfirmDelete(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("touchstart", onPointerDown, { passive: true });
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
    };
  }, [menuOpen, renaming]);

  const renameMutation = useMutation({
    mutationFn: (newTitle: string) => renameThread(token!, threadId, newTitle),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      queryClient.invalidateQueries({ queryKey: ["thread", threadId] });
      setRenaming(false);
      setMenuOpen(false);
      setError("");
    },
    onError: (e: Error) => setError(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteThread(token!, threadId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      setMenuOpen(false);
      setConfirmDelete(false);
      if (activeThreadId === threadId) {
        navigate("/history", { replace: true });
      }
    },
    onError: (e: Error) => setError(e.message),
  });

  useEffect(() => {
    if (!renaming) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !renameMutation.isPending) setRenaming(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [renaming, renameMutation.isPending]);

  const openRename = () => {
    setDraftTitle(title);
    setMenuOpen(false);
    setConfirmDelete(false);
    setRenaming(true);
    setError("");
  };

  const submitRename = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = draftTitle.trim();
    if (!trimmed) {
      setError(t("threadTitleRequired"));
      return;
    }
    if (trimmed === title) {
      setRenaming(false);
      return;
    }
    renameMutation.mutate(trimmed);
  };

  if (!token) return null;

  const menuStyle: CSSProperties | undefined = menuPlacement
    ? {
        top: menuPlacement.top,
        left: menuPlacement.left,
        transform: menuPlacement.transform,
      }
    : undefined;

  const dropdownPortal =
    menuOpen && menuPlacement
      ? createPortal(
          !confirmDelete ? (
            <div
              ref={menuRef}
              id={menuId}
              className="thread-dropdown thread-dropdown--portal"
              role="menu"
              style={menuStyle}
            >
              <button type="button" role="menuitem" onClick={openRename}>
                <PencilIcon />
                {t("renameThread")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="danger"
                onClick={() => setConfirmDelete(true)}
              >
                <TrashIcon />
                {t("deleteThread")}
              </button>
            </div>
          ) : (
            <div
              ref={menuRef}
              className="thread-dropdown thread-dropdown-confirm thread-dropdown--portal"
              role="dialog"
              aria-label={t("deleteThreadConfirm")}
              style={menuStyle}
            >
              <p>{t("deleteThreadConfirm")}</p>
              <div className="thread-dropdown-actions">
                <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(false)}>
                  {t("cancel")}
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate()}
                >
                  {t("delete")}
                </button>
              </div>
            </div>
          ),
          document.body,
        )
      : null;

  const renamePortal = renaming
    ? createPortal(
        <div
          className="thread-rename-overlay"
          role="dialog"
          aria-label={t("renameThread")}
          onClick={() => !renameMutation.isPending && setRenaming(false)}
        >
          <form
            className="thread-rename-sheet"
            onSubmit={submitRename}
            onClick={(e) => e.stopPropagation()}
          >
            <label className="thread-rename-label" htmlFor={`rename-${threadId}`}>
              {t("renameThread")}
            </label>
            <div className="thread-rename-input-wrap">
              <input
                id={`rename-${threadId}`}
                className="thread-rename-input"
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                maxLength={500}
                autoFocus
              />
              {draftTitle.length > 0 && (
                <button
                  type="button"
                  className="thread-rename-clear"
                  onClick={() => setDraftTitle("")}
                  aria-label={t("clearThreadTitle")}
                  title={t("clearThreadTitle")}
                >
                  <ClearIcon />
                </button>
              )}
            </div>
            {error && <p className="thread-menu-error">{error}</p>}
            <div className="thread-rename-actions">
              <button type="button" className="btn-secondary" onClick={() => setRenaming(false)}>
                {t("cancel")}
              </button>
              <button type="submit" className="btn-primary" disabled={renameMutation.isPending}>
                {t("saveTitle")}
              </button>
            </div>
          </form>
        </div>,
        document.body,
      )
    : null;

  return (
    <div className="thread-history-menu" ref={rootRef}>
      <button
        ref={kebabRef}
        type="button"
        className="kebab-btn"
        aria-label={t("threadActions")}
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
          setConfirmDelete(false);
        }}
      >
        <KebabIcon />
      </button>
      {dropdownPortal}
      {renamePortal}
    </div>
  );
}

function KebabIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="12" cy="5" r="1.75" />
      <circle cx="12" cy="12" r="1.75" />
      <circle cx="12" cy="19" r="1.75" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 20h4l10-10-4-4L4 16v4zM14 6l4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 7h16M9 7V5h6v2M7 7l1 12h8l1-12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
