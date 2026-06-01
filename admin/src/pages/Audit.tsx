import { useEffect, useState } from "react";
import { apiFetch } from "../api";

interface Log {
  id: string;
  admin_email: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditPage {
  items: Log[];
  total: number;
  page: number;
  page_size: number;
}

const PAGE_SIZE = 30;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatResource(log: Log): string {
  const parts = [log.resource_type, log.resource_id].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : "—";
}

export function AuditPage() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AuditPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(PAGE_SIZE),
    });
    apiFetch<AuditPage>(`/api/admin/audit?${params}`)
      .then(setData)
      .catch((err) => {
        setData(null);
        setError(err instanceof Error ? err.message : "Не удалось загрузить аудит");
      })
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const pageFrom = data && data.total > 0 ? (data.page - 1) * data.page_size + 1 : 0;
  const pageTo = data ? Math.min(data.page * data.page_size, data.total) : 0;

  return (
    <div className="admin-page admin-page--audit">
      <header className="admin-page-header">
        <div>
          <h1>Аудит</h1>
          <p className="admin-page-subtitle">Журнал действий администраторов</p>
        </div>
        {data && (
          <div className="admin-page-meta">
            <span className="admin-count-badge">{data.total}</span>
            <span className="hint">записей</span>
          </div>
        )}
      </header>

      {error && <p className="error card">{error}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && data && (
        <>
          <div className="audit-table-wrap">
            <table className="audit-table">
              <colgroup>
                <col className="audit-col-time" />
                <col className="audit-col-admin" />
                <col className="audit-col-action" />
                <col className="audit-col-resource" />
                <col className="audit-col-ip" />
              </colgroup>
              <thead>
                <tr>
                  <th>Время</th>
                  <th>Админ</th>
                  <th>Действие</th>
                  <th>Ресурс</th>
                  <th>IP</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="audit-empty">
                      Записей нет
                    </td>
                  </tr>
                )}
                {data.items.map((log) => (
                  <tr key={log.id}>
                    <td className="audit-cell-time">{formatDate(log.created_at)}</td>
                    <td className="audit-cell-admin">{log.admin_email || "—"}</td>
                    <td className="audit-cell-action">
                      <code className="audit-action-code">{log.action}</code>
                    </td>
                    <td className="audit-cell-resource">
                      <span className="audit-resource-text">{formatResource(log)}</span>
                      {log.details && Object.keys(log.details).length > 0 && (
                        <details className="audit-details">
                          <summary>Подробности</summary>
                          <pre className="audit-details-pre">{JSON.stringify(log.details, null, 2)}</pre>
                        </details>
                      )}
                    </td>
                    <td className="audit-cell-ip">{log.ip_address || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.total > PAGE_SIZE && (
            <div className="admin-pager">
              <button
                type="button"
                className="btn-secondary"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Назад
              </button>
              <span className="admin-pager-info">
                {pageFrom}–{pageTo} из {data.total} · страница {page} из {totalPages}
              </span>
              <button
                type="button"
                className="btn-secondary"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Далее
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
