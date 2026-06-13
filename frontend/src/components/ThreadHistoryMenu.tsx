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
  type PointerEvent as ReactPointerEvent,
} from "react";
import { MoreVertical, Pencil, Trash2, X, Pin, PinOff } from "lucide-react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import { deleteThread, renameThread, pinThread, type ThreadListItem } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  threadId: string;
  title: string;
  pinned?: boolean;
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

export function ThreadHistoryMenu({ threadId, title, pinned = false }: Props) {
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

  const pinMutation = useMutation({
    mutationFn: (newPinned: boolean) => pinThread(token!, threadId, newPinned),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      setMenuOpen(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteThread(token!, threadId),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["threads"] });
      const snapshots = queryClient.getQueriesData<ThreadListItem[]>({ queryKey: ["threads"] });
      queryClient.setQueriesData<ThreadListItem[]>({ queryKey: ["threads"] }, (old) =>
        Array.isArray(old) ? old.filter((item) => item.id !== threadId) : old,
      );
      return { snapshots };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      setMenuOpen(false);
      setConfirmDelete(false);
      setError("");
      if (activeThreadId === threadId) {
        navigate("/history", { replace: true });
      }
    },
    onError: (e: Error, _vars, context) => {
      context?.snapshots?.forEach(([key, data]) => {
        queryClient.setQueryData(key, data);
      });
      setError(e.message);
    },
  });

  const closeMenu = useCallback(() => {
    if (deleteMutation.isPending) return;
    setMenuOpen(false);
    setConfirmDelete(false);
    setError("");
  }, [deleteMutation.isPending]);

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

  const stopMenuPointer = (e: ReactPointerEvent) => {
    e.stopPropagation();
  };

  const menuBackdropPortal =
    menuOpen && !renaming
      ? createPortal(
          <div
            className="thread-menu-backdrop"
            aria-hidden
            onPointerDown={(e) => {
              e.preventDefault();
              closeMenu();
            }}
          />,
          document.body,
        )
      : null;

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
              onPointerDown={stopMenuPointer}
            >
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  openRename();
                }}
              >
                <Pencil size={16} strokeWidth={1.8} />
                {t("renameThread")}
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={pinMutation.isPending}
                onClick={(e) => {
                  e.stopPropagation();
                  pinMutation.mutate(!pinned);
                }}
              >
                {pinned ? <PinOff size={16} strokeWidth={1.8} /> : <Pin size={16} strokeWidth={1.8} />}
                {pinned ? "Открепить" : "Закрепить"}
              </button>
              <button
                type="button"
                role="menuitem"
                className="danger"
                onClick={(e) => {
                  e.stopPropagation();
                  setConfirmDelete(true);
                  setError("");
                }}
              >
                <Trash2 size={16} strokeWidth={1.8} />
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
              onPointerDown={stopMenuPointer}
            >
              <p>{t("deleteThreadConfirm")}</p>
              {error && <p className="thread-menu-error">{error}</p>}
              <div className="thread-dropdown-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={deleteMutation.isPending}
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDelete(false);
                    setError("");
                  }}
                >
                  {t("cancel")}
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={deleteMutation.isPending}
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteMutation.mutate();
                  }}
                >
                  {deleteMutation.isPending ? t("historyDeleting") : t("delete")}
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
          setError("");
        }}
      >
        <KebabIcon />
      </button>
      {menuBackdropPortal}
      {dropdownPortal}
      {renamePortal}
    </div>
  );
}

function KebabIcon() {
  return <MoreVertical width={20} height={20} fill="currentColor" aria-hidden />;
}

function ClearIcon() {
  return <X width={16} height={16} strokeWidth={2} aria-hidden />;
}
