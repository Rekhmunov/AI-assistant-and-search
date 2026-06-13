import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Pin } from "lucide-react";
import { deleteThreadsBulk, fetchThreads, searchThreads } from "../api/client";
import { AuthGate } from "../components/AuthGate";
import { HistoryBulkBar } from "../components/HistoryBulkBar";
import { HistoryBulkDeleteModal } from "../components/HistoryBulkDeleteModal";
import { MobileNewThreadButton } from "../components/MobileNewThreadButton";
import { MobilePageHeader } from "../components/MobilePageHeader";
import { ThreadHistoryMenu } from "../components/ThreadHistoryMenu";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

function dayLabel(date: Date): string {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startYesterday = new Date(startToday);
  startYesterday.setDate(startYesterday.getDate() - 1);
  if (date >= startToday) return t("today");
  if (date >= startYesterday) return t("yesterday");
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export function History() {
  const navigate = useNavigate();
  const { id: activeThreadId } = useParams();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const isDesktop = useDesktopLayout();
  const [historySearchOpen, setHistorySearchOpen] = useState(false);
  const [historySearchQuery, setHistorySearchQuery] = useState("");
  const [debouncedHistorySearch, setDebouncedHistorySearch] = useState("");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["threads"],
    queryFn: () => fetchThreads(token!),
    enabled: !!token,
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedHistorySearch(historySearchQuery.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [historySearchQuery]);

  const { data: searchResults = [], isFetching: isSearching } = useQuery({
    queryKey: ["threads", "search", debouncedHistorySearch],
    queryFn: () => searchThreads(token!, debouncedHistorySearch),
    enabled: !!token && historySearchOpen && debouncedHistorySearch.length > 0,
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => deleteThreadsBulk(token!, ids),
    onSuccess: (_data, ids) => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      setConfirmBulkDelete(false);
      setSelectionMode(false);
      setSelectedIds(new Set());
      if (activeThreadId && ids.includes(activeThreadId)) {
        navigate("/history", { replace: true });
      }
    },
  });

  const inMax = isMaxWebApp();
  const isFiltering = historySearchOpen && debouncedHistorySearch.length > 0;
  const visibleThreads = isFiltering ? searchResults : threads;
  const selectedCount = selectedIds.size;

  const exitSelectionMode = () => {
    setSelectionMode(false);
    setSelectedIds(new Set());
    setConfirmBulkDelete(false);
    bulkDeleteMutation.reset();
  };

  const enterSelectionMode = () => {
    setHistorySearchOpen(false);
    setHistorySearchQuery("");
    setDebouncedHistorySearch("");
    setSelectionMode(true);
    setSelectedIds(new Set());
    setConfirmBulkDelete(false);
  };

  const toggleThreadSelected = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedIds(new Set(visibleThreads.map((th) => th.id)));
  };

  const toggleHistorySearch = () => {
    setHistorySearchOpen((open) => {
      if (open) {
        setHistorySearchQuery("");
        setDebouncedHistorySearch("");
      }
      return !open;
    });
  };

  const headerTitle =
    selectionMode && !isDesktop
      ? t("historySelectedCount", { count: selectedCount })
      : t("history");

  const selectButton = (
    <button type="button" className="history-header-select-btn" onClick={enterSelectionMode}>
      {t("historySelect")}
    </button>
  );

  const cancelSelectButton = (
    <button type="button" className="history-header-select-btn" onClick={exitSelectionMode}>
      {t("historyCancelSelect")}
    </button>
  );

  if (!token) {
    return (
      <AuthGate
        title={t("historyGuestGateTitle")}
        primaryTo={inMax ? "/profile" : "/login"}
        primaryLabel={inMax ? t("navProfile") : t("signIn")}
        showPrimary
        showSecondary
        showBrand={false}
      />
    );
  }

  const pinnedThreads = visibleThreads.filter((th) => !!th.pinned_at);
  const unpinnedThreads = visibleThreads.filter((th) => !th.pinned_at);

  const groups = new Map<string, typeof visibleThreads>();
  for (const th of unpinnedThreads) {
    const label = dayLabel(new Date(th.last_message_at));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(th);
  }

  return (
    <div
      className={`page page-history${isDesktop ? "" : " page-history--mobile"}${selectionMode ? " page-history--selecting" : ""}`}
    >
      {isDesktop ? (
        <header className="profile-page-header history-page-header">
          <h1 className="mobile-page-title">
            {selectionMode ? t("historySelectedCount", { count: selectedCount }) : t("history")}
          </h1>
          <div className="history-page-header-actions">
            {selectionMode ? cancelSelectButton : selectButton}
          </div>
        </header>
      ) : (
        <MobilePageHeader
          variant="history"
          title={headerTitle}
          historySearchActive={historySearchOpen}
          onHistorySearchToggle={toggleHistorySearch}
          historySelectionMode={selectionMode}
          rightAction={selectionMode ? cancelSelectButton : selectButton}
        />
      )}

      {isDesktop && selectionMode && (
        <div className="history-bulk-bar-wrap history-bulk-bar-wrap--desktop">
          <HistoryBulkBar
            selectedCount={selectedCount}
            totalVisible={visibleThreads.length}
            deleting={bulkDeleteMutation.isPending}
            onSelectAll={selectAllVisible}
            onClearSelection={() => setSelectedIds(new Set())}
            onDelete={() => setConfirmBulkDelete(true)}
          />
        </div>
      )}

      <div className="history-scroll">
        {!isDesktop && historySearchOpen && !selectionMode && (
          <label className="history-search-bar">
            <SearchFieldIcon />
            <input
              type="search"
              className="history-search-input"
              value={historySearchQuery}
              onChange={(event) => setHistorySearchQuery(event.target.value)}
              placeholder={t("historySearchPlaceholder")}
              autoFocus
              enterKeyHint="search"
            />
          </label>
        )}

        {isLoading && !isFiltering && <p className="muted-text">{t("pageLoading")}</p>}
        {isSearching && isFiltering && <p className="muted-text">{t("pageLoading")}</p>}
        {!isLoading && !isSearching && visibleThreads.length === 0 && (
          <p className="muted-text">{isFiltering ? t("historySearchEmpty") : t("historyEmpty")}</p>
        )}

        {pinnedThreads.length > 0 && (
          <div>
            <div className="section-title history-pinned-label">
              <Pin size={12} strokeWidth={2} aria-hidden />
              {t("historyPinned")}
            </div>
            <ul className="history-list">
              {pinnedThreads.map((th) => {
                const isSelected = selectedIds.has(th.id);
                return (
                  <li key={th.id} className={`history-row${isSelected ? " history-row--selected" : ""}`}>
                    {selectionMode && (
                      <label className="history-row-check">
                        <input type="checkbox" checked={isSelected} onChange={() => toggleThreadSelected(th.id)} aria-label={th.title} />
                      </label>
                    )}
                    <button
                      type="button"
                      className="history-card"
                      onClick={() => {
                        if (selectionMode) { toggleThreadSelected(th.id); return; }
                        navigate(`/thread/${th.id}`, { state: { fromHistory: true } });
                      }}
                    >
                      <span className="history-card-title">
                        <Pin size={12} strokeWidth={2} className="history-pin-icon" aria-hidden />
                        {th.title}
                        {th.thread_type === "agent" && (
                          <span className="history-card-badge">{t("agentThreadBadge")}</span>
                        )}
                      </span>
                      <small className="history-card-meta">
                        {th.message_count} {t("questionsCount")} •{" "}
                        {new Date(th.last_message_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                      </small>
                    </button>
                    {!selectionMode && <ThreadHistoryMenu threadId={th.id} title={th.title} pinned={true} />}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {[...groups.entries()].map(([label, items]) => (
          <div key={label}>
            <div className="section-title">{label}</div>
            <ul className="history-list">
              {items.map((th) => {
                const isSelected = selectedIds.has(th.id);
                return (
                  <li
                    key={th.id}
                    className={`history-row${selectionMode ? " history-row--selecting" : ""}${isSelected ? " history-row--selected" : ""}`}
                  >
                    {selectionMode && (
                      <label className="history-row-check">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleThreadSelected(th.id)}
                          aria-label={th.title}
                        />
                      </label>
                    )}
                    <button
                      type="button"
                      className="history-card"
                      onClick={() => {
                        if (selectionMode) {
                          toggleThreadSelected(th.id);
                          return;
                        }
                        navigate(`/thread/${th.id}`, { state: { fromHistory: true } });
                      }}
                    >
                      <span className="history-card-title">
                        {th.title}
                        {th.thread_type === "agent" && (
                          <span className="history-card-badge">{t("agentThreadBadge")}</span>
                        )}
                      </span>
                      <small className="history-card-meta">
                        {th.message_count} {t("questionsCount")} •{" "}
                        {new Date(th.last_message_at).toLocaleTimeString("ru-RU", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </small>
                    </button>
                    {!selectionMode && <ThreadHistoryMenu threadId={th.id} title={th.title} pinned={false} />}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {!isDesktop && selectionMode && (
        <div className="history-bulk-bar-wrap">
          <HistoryBulkBar
            selectedCount={selectedCount}
            totalVisible={visibleThreads.length}
            deleting={bulkDeleteMutation.isPending}
            onSelectAll={selectAllVisible}
            onClearSelection={() => setSelectedIds(new Set())}
            onDelete={() => setConfirmBulkDelete(true)}
          />
        </div>
      )}

      <HistoryBulkDeleteModal
        open={confirmBulkDelete}
        count={selectedCount}
        deleting={bulkDeleteMutation.isPending}
        onConfirm={() => bulkDeleteMutation.mutate([...selectedIds])}
        onCancel={() => setConfirmBulkDelete(false)}
      />

      {!isDesktop && !selectionMode && (
        <div className="mobile-new-thread-bar mobile-new-thread-bar--docked">
          <MobileNewThreadButton variant="labeled" onClick={() => navigate("/")} />
        </div>
      )}
    </div>
  );
}

function SearchFieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="2" />
      <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
