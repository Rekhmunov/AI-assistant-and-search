import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../api";
import {
  UserThreadDebugPanel,
  type ThreadSummary,
} from "../components/UserThreadDebugPanel";
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
  const [showDeleted, setShowDeleted] = useState(true);
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState("");
  const [systemStatus, setSystemStatus] = useState<{
    messages_debug_trace_column: boolean;
    thread_debug_api: boolean;
    hint: string | null;
  } | null>(null);

  const load = () => {
    if (!id) return;
    apiFetch<UserRow>(`/api/admin/users/${id}`).then(setUser);
    const params = new URLSearchParams({ limit: "50" });
    if (showDeleted) params.set("include_deleted", "true");
    else params.set("include_deleted", "false");
    apiFetch<ThreadSummary[]>(`/api/admin/users/${id}/threads?${params}`).then(setThreads);
  };

  useEffect(load, [id, showDeleted]);

  useEffect(() => {
    apiFetch<{
      messages_debug_trace_column: boolean;
      thread_debug_api: boolean;
      hint: string | null;
    }>("/api/admin/system/status")
      .then(setSystemStatus)
      .catch(() => setSystemStatus(null));
  }, []);

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

  const syncProPayment = async () => {
    if (!id) return;
    setMsg("");
    try {
      const result = await apiFetch<{ ok: boolean; message?: string; source?: string; payment_id?: string }>(
        `/api/admin/users/${id}/sync-pro-payment`,
        { method: "POST" }
      );
      if (result.ok) {
        setMsg(
          result.payment_id
            ? `Pro восстановлен (платёж ${result.payment_id}${result.source ? `, ${result.source}` : ""})`
            : "Pro уже активен"
        );
        load();
        return;
      }
      setMsg(result.message || "Успешная оплата не найдена");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Не удалось синхронизировать оплату");
    }
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
    <div className="user-detail">
      <Link to="/users">← Пользователи</Link>
      <h1>{displayName(user)}</h1>
      <div className="user-detail-summary card">
        <p className="hint">
          {user.email && <>Email: {user.email} · </>}
          {user.max_user_id != null ? <>MAX ID: {user.max_user_id}</> : "MAX не привязан"}
          {user.is_guest && " · гостевая сессия"}
        </p>
        <div className="user-detail-stats">
          <span>
            План: <strong>{user.plan}</strong>
          </span>
          <span>
            Поиски:{" "}
            <strong>
              {user.searches_today}/{user.searches_limit || "—"}
            </strong>
          </span>
          <span>
            Активных тредов: <strong>{user.threads_count}</strong>
          </span>
        </div>
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
          {can("payments:write") && (
            <button type="button" className="btn-secondary" onClick={() => void syncProPayment()}>
              Синхронизировать оплату ЮKassa
            </button>
          )}
          <button type="button" className="btn-secondary" onClick={toggleBan}>
            {user.deleted_at ? "Разбанить" : "Забанить"}
          </button>
        </div>
      )}

      <h2>Треды и отладка ({threads.length})</h2>

      {systemStatus && !systemStatus.messages_debug_trace_column && (
        <p className="error card">
          <strong>БД не обновлена.</strong> {systemStatus.hint || "alembic upgrade head"}
          <br />
          Без миграции 006 расшифровка не сохраняется.
        </p>
      )}

      {systemStatus === null && (
        <p className="error card">
          <strong>Старый backend.</strong> Нет <code>/api/admin/system/status</code> — обновите backend и
          admin на сервере (<code>git pull && docker compose up -d --build backend admin</code>).
        </p>
      )}

      <p className="hint">
        <strong>Нажмите на строку треда</strong> (▶ слева) — откроется вопрос, ответ, запрос в Yandex Search
        и GPT. Если видите только список без ▶ — пересоберите контейнер <code>admin</code>.
      </p>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={showDeleted}
          onChange={(e) => setShowDeleted(e.target.checked)}
        />
        Показывать удалённые пользователем
      </label>

      {threads.length === 0 && <p className="hint">Тредов нет</p>}
      <div className="thread-panels">
        {threads.map((t) => (
          <UserThreadDebugPanel key={t.id} userId={id!} thread={t} />
        ))}
      </div>
    </div>
  );
}
