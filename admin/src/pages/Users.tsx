import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
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
  deleted_at: string | null;
  is_guest: boolean;
}

function accountLabel(u: UserRow): string {
  if (u.email) return u.email;
  if (u.max_user_id != null) return `MAX ${u.max_user_id}`;
  if (u.is_guest) return "гость";
  return "—";
}

export function UsersPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (q: string) => {
    setError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (q) params.set("search", q);
      const data = await apiFetch<UserRow[]>(`/api/admin/users?${params}`);
      setUsers(data);
    } catch (e) {
      setError(String(e));
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    load(search);
  };

  return (
    <div>
      <h1>Пользователи</h1>
      <form className="row" onSubmit={onSearch}>
        <input
          placeholder="email, username или MAX ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="btn-primary">
          Найти
        </button>
        <button type="button" className="btn-secondary" onClick={() => load("")}>
          Обновить
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {loading && <p>Загрузка…</p>}
      {!loading && users.length === 0 && !error && <p className="hint">Пользователей нет</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Аккаунт</th>
            <th>MAX ID</th>
            <th>Имя</th>
            <th>План</th>
            <th>Поиски сегодня</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className={u.deleted_at ? "banned" : ""}>
              <td>{accountLabel(u)}</td>
              <td>{u.max_user_id ?? "—"}</td>
              <td>
                {u.first_name || "—"} {u.username ? `@${u.username}` : ""}
                {u.is_guest && <span className="badge">гость</span>}
              </td>
              <td>
                {u.plan}
                {u.plan_expires_at && <small> до {new Date(u.plan_expires_at).toLocaleDateString()}</small>}
              </td>
              <td>{u.searches_today}</td>
              <td>
                {can("users:read") && <Link to={`/users/${u.id}`}>Открыть</Link>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
