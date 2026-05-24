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

export function AuditPage() {
  const [logs, setLogs] = useState<Log[]>([]);

  useEffect(() => {
    apiFetch<Log[]>("/api/admin/audit").then(setLogs);
  }, []);

  return (
    <div>
      <h1>Аудит</h1>
      <table className="table">
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
          {logs.map((l) => (
            <tr key={l.id}>
              <td>{new Date(l.created_at).toLocaleString()}</td>
              <td>{l.admin_email}</td>
              <td>{l.action}</td>
              <td>
                {l.resource_type} {l.resource_id}
                {l.details && <pre className="small">{JSON.stringify(l.details)}</pre>}
              </td>
              <td>{l.ip_address}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
