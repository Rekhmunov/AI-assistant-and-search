import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { AdminRole, AdminUser, useAuth } from "../AuthContext";

export function AdminsPage() {
  const { can } = useAuth();
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminRole>("support");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = () =>
    apiFetch<AdminUser[]>("/api/admin/admins")
      .then(setAdmins)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить список администраторов"));

  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setMsg("");
    try {
      await apiFetch("/api/admin/admins", {
        method: "POST",
        body: JSON.stringify({ email, password, role }),
      });
      setEmail("");
      setPassword("");
      setMsg("Администратор создан");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать администратора");
    }
  };

  return (
    <div className="admin-page admin-page--admins">
      <header className="admin-page-header">
        <div>
          <h1>Администраторы</h1>
          <p className="admin-page-subtitle">Учётные записи с доступом к панели</p>
        </div>
      </header>
      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}
      {can("admins:write") && (
        <form className="card admins-create-form" onSubmit={create}>
          <h2>Новый админ</h2>
          <input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input
            type="password"
            placeholder="пароль (мин. 8)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
          <select value={role} onChange={(e) => setRole(e.target.value as AdminRole)}>
            <option value="owner">owner</option>
            <option value="support">support</option>
            <option value="marketing">marketing</option>
          </select>
          <button type="submit" className="btn-primary">
            Создать
          </button>
        </form>
      )}
      <div className="admins-table-wrap admin-table-wrap">
        <table className="table admins-table admin-responsive-table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Роль</th>
              <th>Активен</th>
              <th>Последний вход</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => (
              <tr key={a.id}>
                <td data-label="Email">{a.email}</td>
                <td data-label="Роль">{a.role}</td>
                <td data-label="Активен">{a.is_active ? "да" : "нет"}</td>
                <td data-label="Последний вход">
                  {a.last_login_at ? new Date(a.last_login_at).toLocaleString("ru-RU") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
