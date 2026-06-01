import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../api";
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
  deleted_at: string | null;
  is_guest: boolean;
}

function accountLabel(u: UserRow): string {
  if (u.email) return u.email;
  if (u.username) return `@${u.username}`;
  if (u.max_user_id != null) return `MAX ${u.max_user_id}`;
  if (u.first_name) return u.first_name;
  if (u.is_guest) return "Гостевая сессия";
  return "—";
}

function accountInitial(u: UserRow): string {
  const label = accountLabel(u);
  const ch = label.replace(/^@/, "").trim()[0];
  return ch ? ch.toUpperCase() : "?";
}

function displayName(u: UserRow): string {
  const full = [u.first_name, u.last_name].filter(Boolean).join(" ");
  return full || "—";
}

function planLabel(plan: string): string {
  if (plan === "pro") return "Pro";
  if (plan === "free") return "Free";
  return plan;
}

function usagePercent(used: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

export function UsersPage() {
  const { can, admin } = useAuth();
  const [search, setSearch] = useState("");
  const [includeGuests, setIncludeGuests] = useState(false);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (q: string, guests: boolean) => {
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (q) params.set("search", q);
      if (guests) params.set("include_guests", "true");
      const data = await apiFetch<UserRow[]>(`/api/admin/users?${params}`);
      setUsers(Array.isArray(data) ? data : []);
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 403) {
          setError("Нет прав users:read. Нужна роль owner или support.");
        } else if (e.status === 401) {
          setError("Сессия истекла — войдите снова.");
        } else {
          setError(`Ошибка API (${e.status}): ${e.message}`);
        }
      } else {
        setError(String(e));
      }
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!can("users:read")) {
      setLoading(false);
      return;
    }
    load("", includeGuests);
  }, [load, can, includeGuests]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    load(search, includeGuests);
  };

  if (!can("users:read")) {
    return (
      <div className="admin-page">
        <h1>Пользователи</h1>
        <p className="error">
          У роли <strong>{admin?.role}</strong> нет доступа. Войдите как owner или support.
        </p>
      </div>
    );
  }

  return (
    <div className="admin-page admin-page--users">
      <header className="admin-page-header">
        <div>
          <h1>Пользователи</h1>
          <p className="admin-page-subtitle">
            Аккаунты с email или MAX. Гостевые сессии — по фильтру ниже.
          </p>
        </div>
        {!loading && (
          <div className="admin-page-meta">
            <span className="admin-count-badge">{users.length}</span>
            <span className="hint">найдено</span>
          </div>
        )}
      </header>

      <div className="users-toolbar card">
        <form className="users-toolbar-form" onSubmit={onSearch}>
          <label className="users-search-field">
            <span className="users-field-label">Поиск</span>
            <input
              placeholder="email, @username, MAX ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className="checkbox users-checkbox">
            <input
              type="checkbox"
              checked={includeGuests}
              onChange={(e) => setIncludeGuests(e.target.checked)}
            />
            Гостевые сессии
          </label>
          <div className="users-toolbar-actions">
            <button type="submit" className="btn-primary">
              Найти
            </button>
            <button type="button" className="btn-secondary" onClick={() => load(search, includeGuests)}>
              Обновить
            </button>
          </div>
        </form>
      </div>

      {error && <p className="error card">{error}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && users.length === 0 && !error && (
        <div className="card users-empty">
          <p className="hint">Пользователей не найдено</p>
        </div>
      )}

      {!loading && users.length > 0 && (
        <div className="users-table-wrap">
          <table className="users-table">
            <thead>
              <tr>
                <th>Пользователь</th>
                <th>Имя</th>
                <th>План</th>
                <th>Поиски сегодня</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const usage = usagePercent(u.searches_today, u.searches_limit);
                const highUsage = usage >= 90;
                return (
                  <tr key={u.id} className={u.deleted_at ? "users-row--banned" : undefined}>
                    <td>
                      <div className="users-account-cell">
                        <span className="users-avatar" aria-hidden>
                          {accountInitial(u)}
                        </span>
                        <div className="users-account-meta">
                          <span className="users-account-label">{accountLabel(u)}</span>
                          <span className="users-account-id">{u.id.slice(0, 8)}…</span>
                          {u.is_guest && <span className="users-badge users-badge--guest">гость</span>}
                          {u.deleted_at && <span className="users-badge users-badge--banned">заблокирован</span>}
                        </div>
                      </div>
                    </td>
                    <td className="users-cell-name">{displayName(u)}</td>
                    <td>
                      <div className="users-plan-cell">
                        <span className={`plan-badge plan-badge--${u.plan}`}>{planLabel(u.plan)}</span>
                        {u.plan_expires_at && (
                          <span className="users-plan-expires">
                            до {new Date(u.plan_expires_at).toLocaleDateString("ru-RU")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="users-usage">
                        <span className="users-usage-value">
                          {u.searches_today}
                          {u.searches_limit > 0 ? ` / ${u.searches_limit}` : ""}
                        </span>
                        {u.searches_limit > 0 && (
                          <div
                            className="users-usage-bar"
                            role="progressbar"
                            aria-valuenow={u.searches_today}
                            aria-valuemin={0}
                            aria-valuemax={u.searches_limit}
                          >
                            <div
                              className={`users-usage-fill${highUsage ? " users-usage-fill--high" : ""}`}
                              style={{ width: `${usage}%` }}
                            />
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="users-cell-action">
                      <Link className="btn-secondary btn-secondary--compact users-open-link" to={`/users/${u.id}`}>
                        Открыть
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
