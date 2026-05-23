import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL || "";
const ADMIN_KEY = import.meta.env.VITE_ADMIN_API_KEY || "dev-admin-key";

interface Metrics {
  users_total: number;
  users_pro: number;
  broadcasts_total: number;
}

interface Broadcast {
  id: string;
  text: string;
  audience: string;
  status: string;
  sent_count: number;
  failed_count: number;
}

export default function App() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [broadcasts, setBroadcasts] = useState<Broadcast[]>([]);
  const [text, setText] = useState("");

  const headers = { "Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY };

  const load = async () => {
    const [m, b] = await Promise.all([
      fetch(`${API}/api/admin/metrics`, { headers }).then((r) => r.json()),
      fetch(`${API}/api/admin/broadcasts`, { headers }).then((r) => r.json()),
    ]);
    setMetrics(m);
    setBroadcasts(b);
  };

  useEffect(() => {
    load();
  }, []);

  const createBroadcast = async () => {
    await fetch(`${API}/api/admin/broadcasts`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text, audience: "all" }),
    });
    setText("");
    load();
  };

  const send = async (id: string) => {
    await fetch(`${API}/api/admin/broadcasts/${id}/send`, { method: "POST", headers });
    load();
  };

  return (
    <div style={{ fontFamily: "sans-serif", maxWidth: 800, margin: "24px auto", padding: 16 }}>
      <h1>AI Search — Admin</h1>
      {metrics && (
        <ul>
          <li>Пользователей: {metrics.users_total}</li>
          <li>Pro: {metrics.users_pro}</li>
          <li>Рассылок: {metrics.broadcasts_total}</li>
        </ul>
      )}
      <h2>Новая рассылка</h2>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} style={{ width: "100%" }} />
      <button type="button" onClick={createBroadcast} disabled={!text.trim()}>
        Создать
      </button>
      <h2>Рассылки</h2>
      {broadcasts.map((b) => (
        <div key={b.id} style={{ border: "1px solid #ccc", padding: 12, marginBottom: 8 }}>
          <p>{b.text}</p>
          <small>
            {b.status} • sent {b.sent_count} • failed {b.failed_count}
          </small>
          {b.status === "draft" && (
            <div>
              <button type="button" onClick={() => send(b.id)}>
                Отправить
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
