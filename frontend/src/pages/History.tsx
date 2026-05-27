import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { fetchThreads } from "../api/client";
import { ThreadHistoryMenu } from "../components/ThreadHistoryMenu";
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

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["threads"],
    queryFn: () => fetchThreads(token!),
    enabled: !!token,
  });

  const inMax = isMaxWebApp();

  if (!token) {
    return (
      <div className="page">
        <h1>{t("history")}</h1>
        <p className="auth-gate-text">{t("historyLoginHint")}</p>
        {!inMax && (
          <Link to="/login" className="btn-primary btn-block">
            {t("signIn")}
          </Link>
        )}
        {inMax && (
          <Link to="/profile" className="btn-primary btn-block">
            {t("navProfile")}
          </Link>
        )}
        <Link to="/" className="btn-link" style={{ display: "block", marginTop: 16, textAlign: "center" }}>
          {t("backToSearch")}
        </Link>
      </div>
    );
  }

  const groups = new Map<string, typeof threads>();
  for (const th of threads) {
    const label = dayLabel(new Date(th.last_message_at));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(th);
  }

  return (
    <div className="page page-history">
      <h1>{t("history")}</h1>
      {isLoading && <p className="muted-text">{t("loading")}</p>}
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
  );
}
