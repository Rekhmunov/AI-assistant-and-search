import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchThreads } from "../api/client";
import { AuthGate, HistoryGateIcon } from "../components/AuthGate";
import { MobilePageHeader } from "../components/MobilePageHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { ThreadHistoryMenu } from "../components/ThreadHistoryMenu";
import { getHomePlaceholderPhrases } from "../constants/homePlaceholders";
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
  const [query, setQuery] = useState("");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const placeholderPhrases = useMemo(() => getHomePlaceholderPhrases(), []);

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["threads"],
    queryFn: () => fetchThreads(token!),
    enabled: !!token,
  });

  const inMax = isMaxWebApp();
  const hasDraft = Boolean(query.trim() || attachments.length > 0);

  const startSearch = (payload: { query: string; attachmentIds: string[] }) => {
    if (!payload.query.trim() && payload.attachmentIds.length > 0) {
      return;
    }
    const params = new URLSearchParams();
    params.set("q", payload.query);
    if (payload.attachmentIds.length) {
      params.set("files", payload.attachmentIds.join(","));
    }
    navigate(`/thread?${params.toString()}`);
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

  const groups = new Map<string, typeof threads>();
  for (const th of threads) {
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
        <MobilePageHeader variant="history" title={t("history")} />
      )}

      <div className="history-scroll">
        {isLoading && <p className="muted-text">{t("pageLoading")}</p>}
        {!isLoading && threads.length === 0 && <p className="muted-text">{t("historyEmpty")}</p>}
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
        <SearchComposer
          value={query}
          onChange={setQuery}
          onSubmit={startSearch}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          layoutMode="threadMobile"
          onNewChat={() => navigate("/")}
          animatedPlaceholder={!hasDraft}
          placeholderPhrases={placeholderPhrases}
          requireTextWithAttachments
        />
      )}
    </div>
  );
}
