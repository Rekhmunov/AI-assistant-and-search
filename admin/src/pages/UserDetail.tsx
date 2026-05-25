import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

interface UserRow {
  id: string;
  max_user_id: number | null;
  email: string | null;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  plan: string;
  plan_expires_at: string | null;
  searches_today: number;
  deleted_at: string | null;
  is_guest: boolean;
}

interface ThreadRow {
  id: string;
  title: string;
  message_count: number;
  last_message_at: string;
}

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [user, setUser] = useState<UserRow | null>(null);
  const [threads, setThreads] = useState<ThreadRow[]>([]);
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState("");

  const load = () => {
    if (!id) return;
    apiFetch<UserRow>(`/api/admin/users/${id}`).then(setUser);
    apiFetch<ThreadRow[]>(`/api/admin/users/${id}/threads`).then(setThreads);
  };

  useEffect(load, [id]);

  const grantPro = async (e: FormEvent) => {
    e.preventDefault();
    if (!id) return;
    await apiFetch(`/api/admin/users/${id}/grant-pro`, {
      method: "POST",
      body: JSON.stringify({ days }),
    });
    setMsg("Pro выдан");
    load();
  };

  const toggleBan = async () => {
    if (!id || !user) return;
    await apiFetch(`/api/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ banned: !user.deleted_at }),
    });
    load();
  };

  if (!user) return <p>Загрузка…</p>;

  return (
    <div>
      <Link to="/users">← Пользователи</Link>
      <h1>
        {user.first_name || "Пользователь"} {user.last_name || ""}
      </h1>
      <p className="hint">
        {user.email && <>Email: {user.email} · </>}
        {user.max_user_id != null ? <>MAX ID: {user.max_user_id}</> : "MAX не привязан"}
        {user.is_guest && " · гостевая сессия"}
      </p>
      <p>
        План: <strong>{user.plan}</strong> · Поисков сегодня: {user.searches_today}
        {user.deleted_at && <span className="badge bad">забанен</span>}
      </p>
      {msg && <p className="ok">{msg}</p>}
      {can("users:write") && (
        <div className="card row-actions">
          <form onSubmit={grantPro} className="row">
            <label>
              Выдать Pro на дней
              <input type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            </label>
            <button type="submit" className="btn-primary">
              Выдать Pro
            </button>
          </form>
          <button type="button" className="btn-secondary" onClick={toggleBan}>
            {user.deleted_at ? "Разбанить" : "Забанить"}
          </button>
        </div>
      )}
      <h2>Треды</h2>
      <ul>
        {threads.map((t) => (
          <li key={t.id}>
            {t.title} ({t.message_count}) — {new Date(t.last_message_at).toLocaleString()}
          </li>
        ))}
      </ul>
    </div>
  );
}
