import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

interface UserRow {
  id: string;
  max_user_id: number;
  username: string | null;
  first_name: string | null;
  plan: string;
  plan_expires_at: string | null;
  searches_today: number;
  deleted_at: string | null;
}

export function UsersPage() {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [users, setUsers] = useState<UserRow[]>([]);
  const [error, setError] = useState("");

  const load = async (q: string) => {
    setError("");
    try {
      const params = new URLSearchParams();
      if (q) params.set("search", q);
      const data = await apiFetch<UserRow[]>(`/api/admin/users?${params}`);
      setUsers(data);
    } catch (e) {
      setError(String(e));
    }
  };

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    load(search);
  };

  return (
    <div>
      <h1>Пользователи</h1>
      <form className="row" onSubmit={onSearch}>
        <input
          placeholder="username или max_user_id"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="btn-primary">
          Найти
        </button>
        <button type="button" className="btn-secondary" onClick={() => load("")}>
          Сброс
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      <table className="table">
        <thead>
          <tr>
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
              <td>{u.max_user_id}</td>
              <td>
                {u.first_name || "—"} {u.username ? `@${u.username}` : ""}
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
