import { useEffect, useState } from "react";
import { apiFetch } from "../api";

interface FeedbackReasonStat {
  reason_code: string | null;
  label: string;
  count: number;
}

interface FeedbackRecentItem {
  id: string;
  message_id: string;
  thread_id: string;
  user_id: string;
  user_email: string | null;
  rating: string;
  reason_label: string | null;
  comment: string | null;
  answer_preview: string;
  created_at: string;
}

interface FeedbackRecentPage {
  items: FeedbackRecentItem[];
  total: number;
  page: number;
  page_size: number;
}

interface FeedbackDashboardBlock {
  thumbs_up: number;
  thumbs_down: number;
  down_by_reason: FeedbackReasonStat[];
  recent_total: number;
}

interface DashboardMetrics {
  users_total: number;
  users_new_7d: number;
  users_pro: number;
  users_active_24h: number;
  broadcasts_total: number;
  messages_today: number;
  searches_today_estimate: number;
  answer_feedback: FeedbackDashboardBlock;
}

const RECENT_PAGE_SIZE = 30;

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");
  const [recentOpen, setRecentOpen] = useState(false);
  const [recentPage, setRecentPage] = useState(1);
  const [recentData, setRecentData] = useState<FeedbackRecentPage | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentError, setRecentError] = useState("");

  useEffect(() => {
    apiFetch<DashboardMetrics>("/api/admin/dashboard")
      .then(setData)
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg === "Internal server error" ? `${msg} — обновите сервер и миграции БД` : msg);
      });
  }, []);

  useEffect(() => {
    if (!recentOpen) return;
    setRecentLoading(true);
    setRecentError("");
    apiFetch<FeedbackRecentPage>(
      `/api/admin/dashboard/feedback-recent?page=${recentPage}&page_size=${RECENT_PAGE_SIZE}`,
    )
      .then(setRecentData)
      .catch((e) => {
        setRecentError(e instanceof Error ? e.message : String(e));
        setRecentData(null);
      })
      .finally(() => setRecentLoading(false));
  }, [recentOpen, recentPage]);

  const toggleRecent = () => {
    setRecentOpen((open) => {
      if (open) return false;
      setRecentPage(1);
      return true;
    });
  };

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>Загрузка метрик…</p>;

  const fb = data.answer_feedback ?? {
    thumbs_up: 0,
    thumbs_down: 0,
    down_by_reason: [],
    recent_total: 0,
  };
  const downTotal = fb.thumbs_down || 0;
  const recentTotalPages = recentData
    ? Math.max(1, Math.ceil(recentData.total / recentData.page_size))
    : Math.max(1, Math.ceil(fb.recent_total / RECENT_PAGE_SIZE));

  return (
    <div>
      <h1>Дашборд</h1>
      <div className="grid">
        <div className="stat-card">
          <span>Пользователей</span>
          <strong>{data.users_total}</strong>
        </div>
        <div className="stat-card">
          <span>Новых за 7 дней</span>
          <strong>{data.users_new_7d}</strong>
        </div>
        <div className="stat-card">
          <span>Pro</span>
          <strong>{data.users_pro}</strong>
        </div>
        <div className="stat-card">
          <span>Активных 24ч</span>
          <strong>{data.users_active_24h}</strong>
        </div>
        <div className="stat-card">
          <span>Сообщений сегодня</span>
          <strong>{data.messages_today}</strong>
        </div>
        <div className="stat-card">
          <span>Рассылок</span>
          <strong>{data.broadcasts_total}</strong>
        </div>
      </div>

      <section className="feedback-dashboard card" aria-labelledby="feedback-dashboard-title">
        <div className="feedback-dashboard-header">
          <h2 id="feedback-dashboard-title">Оценки ответов</h2>
          <p className="feedback-dashboard-sub">Реакции пользователей на ответы ассистента</p>
        </div>
        <div className="feedback-dashboard-stats">
          <div className="feedback-stat feedback-stat--up">
            <span className="feedback-stat-icon" aria-hidden>
              👍
            </span>
            <div>
              <strong>{fb.thumbs_up}</strong>
              <span>Полезно</span>
            </div>
          </div>
          <div className="feedback-stat feedback-stat--down">
            <span className="feedback-stat-icon" aria-hidden>
              👎
            </span>
            <div>
              <strong>{fb.thumbs_down}</strong>
              <span>Не полезно</span>
            </div>
          </div>
        </div>
        {fb.down_by_reason.length > 0 && (
          <div className="feedback-reasons">
            <h3>Причины «не полезно»</h3>
            <ul className="feedback-reason-bars">
              {fb.down_by_reason.map((r) => {
                const pct = downTotal > 0 ? Math.round((r.count / downTotal) * 100) : 0;
                return (
                  <li key={r.reason_code ?? r.label}>
                    <div className="feedback-reason-row">
                      <span className="feedback-reason-label">{r.label}</span>
                      <span className="feedback-reason-count">
                        {r.count} ({pct}%)
                      </span>
                    </div>
                    <div className="feedback-reason-track">
                      <div className="feedback-reason-fill" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {fb.recent_total > 0 ? (
          <div className="feedback-recent">
            <button
              type="button"
              className="feedback-recent-toggle"
              onClick={toggleRecent}
              aria-expanded={recentOpen}
            >
              <span className={`feedback-recent-chevron${recentOpen ? " feedback-recent-chevron--open" : ""}`} aria-hidden>
                ▶
              </span>
              <span className="feedback-recent-toggle-title">Последние оценки</span>
              <span className="feedback-recent-toggle-count">{fb.recent_total}</span>
            </button>
            {recentOpen && (
              <div className="feedback-recent-body">
                {recentLoading && <p className="feedback-recent-loading">Загрузка…</p>}
                {recentError && <p className="error">{recentError}</p>}
                {!recentLoading && !recentError && recentData && recentData.items.length > 0 && (
                  <>
                    <div className="feedback-recent-table-wrap">
                      <table className="feedback-recent-table">
                        <thead>
                          <tr>
                            <th>Дата</th>
                            <th>Оценка</th>
                            <th>Причина</th>
                            <th>Пользователь</th>
                            <th>Фрагмент ответа</th>
                          </tr>
                        </thead>
                        <tbody>
                          {recentData.items.map((item) => (
                            <tr key={item.id}>
                              <td className="feedback-recent-date">{formatDate(item.created_at)}</td>
                              <td>
                                <span
                                  className={`feedback-rating-badge feedback-rating-badge--${item.rating}`}
                                >
                                  {item.rating === "up" ? "👍" : "👎"}
                                </span>
                              </td>
                              <td>
                                {item.rating === "down" ? (
                                  <span className="feedback-recent-reason">
                                    {item.reason_label ?? "—"}
                                    {item.comment ? (
                                      <span className="feedback-recent-comment" title={item.comment}>
                                        {item.comment.length > 80
                                          ? `${item.comment.slice(0, 77)}…`
                                          : item.comment}
                                      </span>
                                    ) : null}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td className="feedback-recent-user">
                                {item.user_email ?? item.user_id.slice(0, 8)}
                              </td>
                              <td className="feedback-recent-preview" title={item.answer_preview}>
                                {item.answer_preview || "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {recentData.total > RECENT_PAGE_SIZE && (
                      <div className="feedback-recent-pager">
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={recentPage <= 1 || recentLoading}
                          onClick={() => setRecentPage((p) => Math.max(1, p - 1))}
                        >
                          Назад
                        </button>
                        <span className="feedback-recent-pager-info">
                          Страница {recentPage} из {recentTotalPages}
                        </span>
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={recentPage >= recentTotalPages || recentLoading}
                          onClick={() => setRecentPage((p) => p + 1)}
                        >
                          Далее
                        </button>
                      </div>
                    )}
                  </>
                )}
                {!recentLoading && !recentError && recentData?.items.length === 0 && (
                  <p className="feedback-empty">Нет оценок на этой странице</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="feedback-empty">Пока нет оценок ответов</p>
        )}
      </section>
    </div>
  );
}
