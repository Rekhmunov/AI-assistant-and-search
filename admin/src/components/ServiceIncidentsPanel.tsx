import { useState } from "react";

export interface ServiceIncidentStat {
  service: string;
  service_label: string;
  count_24h: number;
  count_7d: number;
  last_message: string | null;
  last_at: string | null;
}

export interface ServiceIncidentRecentItem {
  service: string;
  service_label: string;
  kind: string;
  message: string;
  status_code: number | null;
  at: string | null;
}

export interface ServiceIncidentsDashboard {
  totals_24h: number;
  by_service: ServiceIncidentStat[];
  recent: ServiceIncidentRecentItem[];
}

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

type Props = {
  incidents: ServiceIncidentsDashboard;
};

export function ServiceIncidentsPanel({ incidents }: Props) {
  const [recentOpen, setRecentOpen] = useState(true);

  return (
    <div className="incidents-panel">
      {incidents.by_service.length > 0 ? (
        <div className="incidents-by-service">
          {incidents.by_service.map((row) => (
            <div key={row.service} className="incidents-service-row">
              <span className="incidents-service-label">{row.service_label}</span>
              <span className="incidents-service-counts">
                24 ч: {row.count_24h} · 7 д: {row.count_7d}
              </span>
              {row.last_message ? (
                <span className="incidents-service-last" title={row.last_message}>
                  {row.last_at ? `${formatDate(row.last_at)} — ` : ""}
                  {row.last_message.length > 120
                    ? `${row.last_message.slice(0, 117)}…`
                    : row.last_message}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="incidents-empty">За последние дни сбоев не зафиксировано</p>
      )}

      {incidents.recent.length > 0 ? (
        <div className="incidents-recent">
          <button
            type="button"
            className="incidents-recent-toggle"
            onClick={() => setRecentOpen((value) => !value)}
            aria-expanded={recentOpen}
          >
            <span
              className={`incidents-recent-chevron${recentOpen ? " incidents-recent-chevron--open" : ""}`}
              aria-hidden
            >
              ▶
            </span>
            Последние события ({incidents.recent.length})
          </button>
          {recentOpen ? (
            <ul className="incidents-recent-list">
              {incidents.recent.map((item, idx) => (
                <li key={`${item.at}-${idx}`} className="incidents-recent-item">
                  <span className="incidents-recent-meta">
                    {item.at ? formatDate(item.at) : "—"} · {item.service_label}
                    {item.status_code ? ` · HTTP ${item.status_code}` : ""}
                  </span>
                  <span className="incidents-recent-msg">{item.message}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
