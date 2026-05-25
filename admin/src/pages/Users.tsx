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
  if (u.is_guest) return "гость";
  return "—";
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
      <div>
        <h1>Пользователи</h1>
        <p className="error">
          У роли <strong>{admin?.role}</strong> нет доступа. Войдите как owner или support.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1>Пользователи</h1>
      <p className="hint">
        По умолчанию только аккаунты с email или MAX — без дублей «гость + @username». Гостевые сессии —
        по галочке ниже.
      </p>
      <form className="row" onSubmit={onSearch}>
        <input
          placeholder="email, @username, MAX ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={includeGuests}
            onChange={(e) => setIncludeGuests(e.target.checked)}
          />
          Гостевые сессии
        </label>
        <button type="submit" className="btn-primary">
          Найти
        </button>
        <button type="button" className="btn-secondary" onClick={() => load("", includeGuests)}>
          Обновить
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {loading && <p>Загрузка…</p>}
      {!loading && users.length === 0 && !error && <p className="hint">Пользователей нет</p>}
      {!loading && users.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Аккаунт</th>
              <th>Имя</th>
              <th>План</th>
              <th>Поиски сегодня</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className={u.deleted_at ? "banned" : ""}>
                <td>
                  {accountLabel(u)}
                  {u.is_guest && <span className="badge">гость</span>}
                </td>
                <td>{u.first_name || "—"}</td>
                <td>
                  {u.plan}
                  {u.plan_expires_at && (
                    <small> до {new Date(u.plan_expires_at).toLocaleDateString()}</small>
                  )}
                </td>
                <td>
                  {u.searches_today}
                  {u.searches_limit > 0 ? ` / ${u.searches_limit}` : ""}
                </td>
                <td>
                  <Link to={`/users/${u.id}`}>Открыть</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
