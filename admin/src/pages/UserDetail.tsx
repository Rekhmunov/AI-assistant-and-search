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
  const full = [user.first_name, user.last_name].filter(Boolean).join(" ");
  if (full) return full;
  if (user.username) return `@${user.username}`;
  if (user.email) return user.email;
  if (user.max_user_id != null) return `MAX ${user.max_user_id}`;
  return "Пользователь";
}

function accountSubtitle(user: UserRow): string {
  const parts: string[] = [];
  if (user.email) parts.push(user.email);
  if (user.max_user_id != null) parts.push(`MAX ${user.max_user_id}`);
  if (user.is_guest) parts.push("гостевая сессия");
  return parts.join(" · ") || "Контакт не указан";
}

function planLabel(plan: string): string {
  if (plan === "pro") return "Pro";
  if (plan === "free") return "Free";
  return plan;
}

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const [user, setUser] = useState<UserRow | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [showDeleted, setShowDeleted] = useState(true);
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [systemStatus, setSystemStatus] = useState<{
    messages_debug_trace_column: boolean;
    thread_debug_api: boolean;
    hint: string | null;
  } | null>(null);

  const load = () => {
    if (!id) return;
    setLoading(true);
    setError("");
    Promise.all([
      apiFetch<UserRow>(`/api/admin/users/${id}`),
      apiFetch<ThreadSummary[]>(
        `/api/admin/users/${id}/threads?${new URLSearchParams({
          limit: "50",
          include_deleted: showDeleted ? "true" : "false",
        })}`,
      ),
    ])
      .then(([userData, threadData]) => {
        setUser(userData);
        setThreads(Array.isArray(threadData) ? threadData : []);
      })
      .catch((err) => {
        setUser(null);
        setThreads([]);
        setError(err instanceof Error ? err.message : "Не удалось загрузить пользователя");
      })
      .finally(() => setLoading(false));
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
    setMsg("");
    setError("");
    try {
      await apiFetch(`/api/admin/users/${id}/grant-pro`, {
        method: "POST",
        body: JSON.stringify({ days }),
      });
      setMsg("Pro выдан");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось выдать Pro");
    }
  };

  const revokePro = async () => {
    if (!id || user?.plan !== "pro") return;
    if (!window.confirm("Отменить подписку Pro у этого пользователя?")) return;
    setMsg("");
    setError("");
    try {
      await apiFetch(`/api/admin/users/${id}/revoke-pro`, { method: "POST" });
      setMsg("Pro отменён");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось отменить Pro");
    }
  };

  const syncProPayment = async () => {
    if (!id) return;
    setMsg("");
    setError("");
    try {
      const result = await apiFetch<{
        ok: boolean;
        plan?: string;
        message?: string;
        source?: string;
        payment_id?: string;
        already_active?: boolean;
      }>(`/api/admin/users/${id}/sync-pro-payment`, { method: "POST" });
      if (result.ok && (result.plan === "pro" || result.already_active)) {
        setMsg(
          result.payment_id
            ? `Pro восстановлен (платёж ${result.payment_id}${result.source ? `, ${result.source}` : ""})`
            : "Pro уже активен",
        );
        load();
        return;
      }
      if (result.ok) {
        setError("Синхронизация прошла, но тариф остался Free — проверьте plan в базе");
        load();
        return;
      }
      setError(result.message || "Успешная оплата не найдена");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось синхронизировать оплату");
    }
  };

  const setPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !user?.email) return;
    setMsg("");
    setError("");
    setPasswordBusy(true);
    try {
      await apiFetch(`/api/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ password: newPassword }),
      });
      setMsg("Пароль обновлён");
      setNewPassword("");
      setShowPasswordForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сменить пароль");
    } finally {
      setPasswordBusy(false);
    }
  };

  const toggleBan = async () => {
    if (!id || !user) return;
    setMsg("");
    setError("");
    try {
      await apiFetch(`/api/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ banned: !user.deleted_at }),
      });
      setMsg(user.deleted_at ? "Пользователь разблокирован" : "Пользователь заблокирован");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить статус блокировки");
    }
  };

  if (loading && !user) {
    return (
      <div className="admin-page admin-page--user-detail">
        <p className="hint">Загрузка…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="admin-page admin-page--user-detail">
        <Link to="/users" className="admin-back-link">
          ← Пользователи
        </Link>
        <p className="error card">{error || "Пользователь не найден"}</p>
      </div>
    );
  }

  return (
    <div className="admin-page admin-page--user-detail">
      <header className="admin-page-header">
        <div>
          <Link to="/users" className="admin-back-link">
            ← Пользователи
          </Link>
          <h1>{displayName(user)}</h1>
          <p className="admin-page-subtitle">{accountSubtitle(user)}</p>
        </div>
        <div className="admin-page-meta user-detail-meta">
          {user.deleted_at && <span className="users-badge users-badge--banned">заблокирован</span>}
          <span className={`plan-badge plan-badge--${user.plan}`}>{planLabel(user.plan)}</span>
        </div>
      </header>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}

      <section className="card user-detail-stats-card">
        <div className="user-detail-stats-grid">
          <div className="user-detail-stat">
            <span className="user-detail-stat-label">Поиски сегодня</span>
            <strong className="user-detail-stat-value">
              {user.searches_today}/{user.searches_limit || "—"}
            </strong>
          </div>
          <div className="user-detail-stat">
            <span className="user-detail-stat-label">Активных тредов</span>
            <strong className="user-detail-stat-value">{user.threads_count}</strong>
          </div>
          {user.plan_expires_at && (
            <div className="user-detail-stat">
              <span className="user-detail-stat-label">Pro до</span>
              <strong className="user-detail-stat-value">
                {new Date(user.plan_expires_at).toLocaleDateString("ru-RU")}
              </strong>
            </div>
          )}
          <div className="user-detail-stat">
            <span className="user-detail-stat-label">ID</span>
            <strong className="user-detail-stat-value user-detail-stat-value--mono">{user.id}</strong>
          </div>
        </div>
      </section>

      {can("users:write") && (
        <section className="card user-detail-section-card">
          <h2 className="user-detail-section-title">Управление аккаунтом</h2>
          <form onSubmit={grantPro} className="user-detail-grant-form">
            <label className="user-detail-field">
              <span className="user-detail-field-label">Выдать Pro на дней</span>
              <input
                type="number"
                min={1}
                max={365}
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
              />
            </label>
            <button type="submit" className="btn-primary">
              Выдать Pro
            </button>
          </form>
          <div className="user-detail-actions-row">
            {user.plan === "pro" && (
              <button type="button" className="btn-secondary btn-danger-outline" onClick={() => void revokePro()}>
                Отменить Pro
              </button>
            )}
            {can("payments:write") && user.plan !== "pro" && (
              <button type="button" className="btn-secondary" onClick={() => void syncProPayment()}>
                Синхронизировать оплату ЮKassa
              </button>
            )}
            {user.email && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setShowPasswordForm((v) => !v);
                  setError("");
                }}
              >
                Сменить пароль
              </button>
            )}
            <button
              type="button"
              className={`btn-secondary${user.deleted_at ? "" : " btn-danger-outline"}`}
              onClick={() => void toggleBan()}
            >
              {user.deleted_at ? "Разбанить" : "Забанить"}
            </button>
          </div>
          {showPasswordForm && user.email && (
            <form className="user-detail-password-form" onSubmit={setPassword}>
              <label className="user-detail-field">
                <span className="user-detail-field-label">Новый пароль</span>
                <input
                  type="password"
                  minLength={8}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  placeholder="мин. 8 символов"
                />
              </label>
              <div className="user-detail-actions-row">
                <button type="submit" className="btn-primary" disabled={passwordBusy}>
                  {passwordBusy ? "…" : "Сохранить пароль"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={passwordBusy}
                  onClick={() => {
                    setShowPasswordForm(false);
                    setNewPassword("");
                  }}
                >
                  Отмена
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      <section className="user-detail-threads-section">
        <header className="user-detail-threads-header">
          <div>
            <h2 className="user-detail-section-title">Треды и отладка</h2>
            <p className="hint user-detail-section-hint">Нажмите на строку треда (▶) — откроется расшифровка.</p>
          </div>
          <span className="admin-count-badge">{threads.length}</span>
        </header>

        {systemStatus && !systemStatus.messages_debug_trace_column && (
          <p className="error card">
            <strong>БД не обновлена.</strong> {systemStatus.hint || "alembic upgrade head"}
            <br />
            Без миграции 006 расшифровка не сохраняется.
          </p>
        )}

        {systemStatus === null && (
          <p className="error card">
            <strong>Старый backend.</strong> Нет <code>/api/admin/system/status</code> — обновите backend и admin на
            сервере.
          </p>
        )}

        <label className="checkbox user-detail-threads-filter">
          <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
          Показывать удалённые пользователем
        </label>

        {threads.length === 0 && <p className="hint card payments-empty">Тредов нет</p>}
        <div className="thread-panels">
          {threads.map((t) => (
            <UserThreadDebugPanel key={t.id} userId={id!} thread={t} />
          ))}
        </div>
      </section>
    </div>
  );
}
