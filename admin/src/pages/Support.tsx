import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type SupportTicket = {
  id: string;
  user_id: string;
  user_email: string | null;
  user_max_user_id: number | null;
  source: string;
  message: string;
  status: "open" | "closed";
  created_at: string;
  closed_at: string | null;
};

const SOURCE_LABELS: Record<string, string> = {
  pro_payment: "Оплата Pro",
  general: "Общее",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

export function SupportPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<SupportTicket[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "open" | "closed">("open");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [closingId, setClosingId] = useState<string | null>(null);
  const canWrite = can("support:write");

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

  const closeTicket = async (id: string) => {
    if (!canWrite) return;
    setClosingId(id);
    setMsg("");
    try {
      await apiFetch(`/api/admin/support/tickets/${id}/close`, { method: "PATCH" });
      setMsg("Тикет закрыт");
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setClosingId(null);
    }
  };

  if (!can("support:read")) {
    return <p>Нет доступа</p>;
  }

  return (
    <div className="support-page">
      <header className="page-header">
        <h1>Поддержка</h1>
        <div className="support-filters">
          <label>
            Статус{" "}
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
              <option value="open">Открытые</option>
              <option value="closed">Закрытые</option>
              <option value="">Все</option>
            </select>
          </label>
        </div>
      </header>

      {msg && <p className="hint">{msg}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && items.length === 0 && (
        <p className="hint card support-empty">Тикетов пока нет</p>
      )}

      <div className="support-ticket-list">
        {items.map((ticket) => (
          <article key={ticket.id} className={`card support-ticket${ticket.status === "closed" ? " support-ticket--closed" : ""}`}>
            <header className="support-ticket-head">
              <div>
                <span className={`support-ticket-status support-ticket-status--${ticket.status}`}>
                  {ticket.status === "open" ? "Открыт" : "Закрыт"}
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
            <p className="support-ticket-message">{ticket.message}</p>
            {ticket.status === "open" && canWrite && (
              <button
                type="button"
                className="btn-secondary"
                disabled={closingId === ticket.id}
                onClick={() => void closeTicket(ticket.id)}
              >
                {closingId === ticket.id ? "…" : "Закрыть тикет"}
              </button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
