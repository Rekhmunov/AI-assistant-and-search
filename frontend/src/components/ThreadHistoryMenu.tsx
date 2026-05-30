import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteThread, renameThread } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  threadId: string;
  title: string;
};

export function ThreadHistoryMenu({ threadId, title }: Props) {
  const menuId = useId();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { id: activeThreadId } = useParams();
  const rootRef = useRef<HTMLDivElement>(null);

  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [draftTitle, setDraftTitle] = useState(title);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraftTitle(title);
  }, [title]);

  useEffect(() => {
    if (!menuOpen && !renaming) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setConfirmDelete(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
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

  return (
    <div className="thread-history-menu" ref={rootRef}>
      <button
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

      {menuOpen && !confirmDelete && (
        <div id={menuId} className="thread-dropdown" role="menu">
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
      )}

      {menuOpen && confirmDelete && (
        <div className="thread-dropdown thread-dropdown-confirm" role="dialog" aria-label={t("deleteThreadConfirm")}>
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
      )}

      {renaming && (
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
        </div>
      )}
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
