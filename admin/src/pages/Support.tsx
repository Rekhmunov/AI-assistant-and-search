import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type SupportReply = {
  id: string;
  author_type: string;
  admin_email: string | null;
  message: string;
  created_at: string;
};

type SupportTicket = {
  id: string;
  user_id: string;
  user_email: string | null;
  user_max_user_id: number | null;
  source: string;
  message: string;
  status: "open" | "in_progress" | "closed";
  created_at: string;
  closed_at: string | null;
  yookassa_payment_id: string | null;
  payment_amount_rub: number | null;
  subscription_id: string | null;
  replies: SupportReply[];
};

const SOURCE_LABELS: Record<string, string> = {
  pro_payment: "Оплата Pro",
  general: "Общее",
};

const STATUS_LABELS: Record<string, string> = {
  open: "Открыт",
  in_progress: "В работе",
  closed: "Закрыт",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

export function SupportPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<SupportTicket[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "open" | "in_progress" | "closed">("active");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [notifyIds, setNotifyIds] = useState("");
  const [notifyBusy, setNotifyBusy] = useState(false);
  const canWrite = can("support:write");
  const canSettings = can("settings:write");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (statusFilter) params.set("status", statusFilter);
      const data = await apiFetch<SupportTicket[]>(`/api/admin/support/tickets?${params}`);
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!canSettings) return;
    apiFetch<{ settings: Record<string, string | number | boolean> }>("/api/admin/settings")
      .then((r) => setNotifyIds(String(r.settings.support_notify_max_user_ids ?? "")))
      .catch(() => {});
  }, [canSettings]);

  const setStatus = async (id: string, status: "open" | "in_progress" | "closed") => {
    if (!canWrite) return;
    setBusyId(id);
    setMsg("");
    try {
      await apiFetch(`/api/admin/support/tickets/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setMsg("Статус обновлён");
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setBusyId(null);
    }
  };

  const sendReply = async (id: string) => {
    if (!canWrite) return;
    const text = (replyDrafts[id] ?? "").trim();
    if (!text) return;
    setBusyId(id);
    setMsg("");
    try {
      await apiFetch(`/api/admin/support/tickets/${id}/replies`, {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      setReplyDrafts((prev) => ({ ...prev, [id]: "" }));
      setMsg("Ответ отправлен");
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setBusyId(null);
    }
  };

  const saveNotifyIds = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSettings) return;
    setNotifyBusy(true);
    setMsg("");
    try {
      await apiFetch("/api/admin/settings", {
        method: "PATCH",
        body: JSON.stringify({
          settings: { support_notify_max_user_ids: notifyIds.trim() },
        }),
      });
      setMsg("Настройки уведомлений сохранены");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setNotifyBusy(false);
    }
  };

  if (!can("support:read")) {
    return <p>Нет доступа</p>;
  }

  return (
    <div className="support-page">
      <header className="page-header">
        <h1>Тикеты</h1>
        <div className="support-filters">
          <label>
            Статус{" "}
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
              <option value="active">Активные</option>
              <option value="open">Открытые</option>
              <option value="in_progress">В работе</option>
              <option value="closed">Закрытые</option>
              <option value="">Все</option>
            </select>
          </label>
        </div>
      </header>

      {canSettings && (
        <form className="card support-notify-form" onSubmit={(e) => void saveNotifyIds(e)}>
          <h2 className="support-notify-title">Уведомления в MAX</h2>
          <p className="hint">
            MAX user_id админов через запятую — им придёт сообщение о новом тикете.
          </p>
          <input
            type="text"
            value={notifyIds}
            onChange={(e) => setNotifyIds(e.target.value)}
            placeholder="123456, 789012"
          />
          <button type="submit" className="btn-secondary" disabled={notifyBusy}>
            {notifyBusy ? "Сохранение…" : "Сохранить"}
          </button>
        </form>
      )}

      {msg && <p className="hint">{msg}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && items.length === 0 && (
        <p className="hint card support-empty">Тикетов пока нет</p>
      )}

      <div className="support-ticket-list">
        {items.map((ticket) => (
          <article
            key={ticket.id}
            className={`card support-ticket${ticket.status === "closed" ? " support-ticket--closed" : ""}`}
          >
            <header className="support-ticket-head">
              <div>
                <span className={`support-ticket-status support-ticket-status--${ticket.status}`}>
                  {STATUS_LABELS[ticket.status] ?? ticket.status}
                </span>
                <span className="support-ticket-source">{SOURCE_LABELS[ticket.source] ?? ticket.source}</span>
              </div>
              <time className="support-ticket-date">{formatDate(ticket.created_at)}</time>
            </header>
            <p className="support-ticket-user">
              <Link to={`/users/${ticket.user_id}`}>{ticket.user_email || "без email"}</Link>
              {ticket.user_max_user_id != null && (
                <span className="support-ticket-max"> · MAX {ticket.user_max_user_id}</span>
              )}
            </p>
            {ticket.yookassa_payment_id && (
              <p className="support-ticket-payment hint">
                Платёж: {ticket.yookassa_payment_id}
                {ticket.payment_amount_rub != null ? ` · ${ticket.payment_amount_rub} ₽` : ""}
              </p>
            )}
            <p className="support-ticket-message">{ticket.message}</p>

            {ticket.replies.length > 0 && (
              <div className="support-ticket-replies">
                <h3 className="support-ticket-replies-title">Ответы</h3>
                {ticket.replies.map((r) => (
                  <div key={r.id} className="support-ticket-reply">
                    <p className="support-ticket-reply-meta">
                      {r.admin_email ?? "Поддержка"} · {formatDate(r.created_at)}
                    </p>
                    <p className="support-ticket-reply-text">{r.message}</p>
                  </div>
                ))}
              </div>
            )}

            {canWrite && ticket.status !== "closed" && (
              <div className="support-ticket-actions">
                <textarea
                  className="support-reply-input"
                  rows={3}
                  placeholder="Ответ пользователю…"
                  value={replyDrafts[ticket.id] ?? ""}
                  onChange={(e) =>
                    setReplyDrafts((prev) => ({ ...prev, [ticket.id]: e.target.value }))
                  }
                />
                <div className="support-ticket-action-row">
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busyId === ticket.id}
                    onClick={() => void sendReply(ticket.id)}
                  >
                    {busyId === ticket.id ? "…" : "Отправить ответ"}
                  </button>
                  {ticket.status !== "in_progress" && (
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={busyId === ticket.id}
                      onClick={() => void setStatus(ticket.id, "in_progress")}
                    >
                      В работу
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busyId === ticket.id}
                    onClick={() => void setStatus(ticket.id, "closed")}
                  >
                    Закрыть
                  </button>
                </div>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
