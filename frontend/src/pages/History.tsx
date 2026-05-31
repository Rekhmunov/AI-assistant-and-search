import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchThreads, searchThreads } from "../api/client";
import { AuthGate, HistoryGateIcon } from "../components/AuthGate";
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
  const token = useAuthStore((s) => s.token);
  const isDesktop = useDesktopLayout();
  const [historySearchOpen, setHistorySearchOpen] = useState(false);
  const [historySearchQuery, setHistorySearchQuery] = useState("");
  const [debouncedHistorySearch, setDebouncedHistorySearch] = useState("");

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

  const inMax = isMaxWebApp();
  const isFiltering = historySearchOpen && debouncedHistorySearch.length > 0;
  const visibleThreads = isFiltering ? searchResults : threads;

  const toggleHistorySearch = () => {
    setHistorySearchOpen((open) => {
      if (open) {
        setHistorySearchQuery("");
        setDebouncedHistorySearch("");
      }
      return !open;
    });
  };

  if (!token) {
    return (
      <AuthGate
        title={t("history")}
        hint={t("historyLoginHint")}
        primaryTo={inMax ? "/profile" : "/login"}
        primaryLabel={inMax ? t("navProfile") : t("signIn")}
        showPrimary
        showSecondary
        icon={<HistoryGateIcon />}
      />
    );
  }

  const groups = new Map<string, typeof visibleThreads>();
  for (const th of visibleThreads) {
    const label = dayLabel(new Date(th.last_message_at));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(th);
  }

  return (
    <div className={`page page-history${isDesktop ? "" : " page-history--mobile"}`}>
      {isDesktop ? (
        <header className="profile-page-header">
          <h1 className="mobile-page-title">{t("history")}</h1>
        </header>
      ) : (
        <MobilePageHeader
          variant="history"
          title={t("history")}
          historySearchActive={historySearchOpen}
          onHistorySearchToggle={toggleHistorySearch}
        />
      )}

      <div className="history-scroll">
        {!isDesktop && historySearchOpen && (
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
        {[...groups.entries()].map(([label, items]) => (
          <div key={label}>
            <div className="section-title">{label}</div>
            <ul className="history-list">
              {items.map((th) => (
                <li key={th.id} className="history-row">
                  <button
                    type="button"
                    className="history-card"
                    onClick={() =>
                      navigate(`/thread/${th.id}`, { state: { fromHistory: true } })
                    }
                  >
                    <span className="history-card-title">{th.title}</span>
                    <small className="history-card-meta">
                      {th.message_count} {t("questionsCount")} •{" "}
                      {new Date(th.last_message_at).toLocaleTimeString("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </small>
                  </button>
                  <ThreadHistoryMenu threadId={th.id} title={th.title} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {!isDesktop && (
        <div className="history-new-thread-bar">
          <MobileNewThreadButton onClick={() => navigate("/")} />
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
