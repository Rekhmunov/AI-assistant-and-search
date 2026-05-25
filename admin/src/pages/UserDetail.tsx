import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import { UserThreadPanel, type ThreadSummary } from "../components/UserThreadPanel";
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
  searches_limit: number;
  threads_count: number;
  deleted_at: string | null;
  is_guest: boolean;
}

function displayName(user: UserRow): string {
  if (user.username) return `@${user.username}`;
  if (user.first_name) return user.first_name;
  if (user.email) return user.email;
  if (user.max_user_id != null) return `MAX ${user.max_user_id}`;
  return "Пользователь";
}

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [user, setUser] = useState<UserRow | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState("");

  const load = () => {
    if (!id) return;
    apiFetch<UserRow>(`/api/admin/users/${id}`).then(setUser);
    apiFetch<ThreadSummary[]>(`/api/admin/users/${id}/threads?limit=50`).then(setThreads);
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

  const searchPairs = Math.ceil(
    threads.reduce((n, t) => n + Math.max(0, t.message_count), 0) / 2,
  );

  return (
    <div className="user-detail">
      <Link to="/users">← Пользователи</Link>
      <h1>{displayName(user)}</h1>
      <div className="user-detail-summary card">
        <p className="hint">
          {user.email && <>Email: {user.email} · </>}
          {user.max_user_id != null ? <>MAX ID: {user.max_user_id}</> : "MAX не привязан"}
          {user.is_guest && " · только гостевая сессия (без email/MAX)"}
        </p>
        <div className="user-detail-stats">
          <span>
            План: <strong>{user.plan}</strong>
            {user.plan_expires_at &&
              ` до ${new Date(user.plan_expires_at).toLocaleDateString("ru-RU")}`}
          </span>
          <span>
            Поиски сегодня:{" "}
            <strong>
              {user.searches_today}/{user.searches_limit || "—"}
            </strong>
          </span>
          <span>
            Диалогов: <strong>{user.threads_count || threads.length}</strong>
          </span>
        </div>
        {user.deleted_at && <span className="badge bad">забанен</span>}
        <p className="hint user-detail-note">
          Счётчик поисков — из Redis за сегодня. Отдельные гостевые строки в списке скрыты: после входа
          диалоги переносятся сюда, старый счётчик гостя не суммируется.
        </p>
      </div>

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

      <h2>Диалоги ({threads.length})</h2>
      <p className="hint">
        Раскройте диалог, чтобы увидеть вопросы и ответы. Данные подгружаются по одному треду — не нагружают
        память.
      </p>
      {threads.length === 0 && <p className="hint">Диалогов пока нет</p>}
      <div className="thread-panels">
        {threads.map((t) => (
          <UserThreadPanel key={t.id} userId={id!} thread={t} />
        ))}
      </div>
      {threads.length > 0 && (
        <p className="hint">≈ {searchPairs} пар вопрос–ответ в загруженных тредах</p>
      )}
    </div>
  );
}
