import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { AdminRole, AdminUser, useAuth } from "../AuthContext";

export function AdminsPage() {
  const { can } = useAuth();
  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminRole>("support");

  const load = () => apiFetch<AdminUser[]>("/api/admin/admins").then(setAdmins);

  useEffect(() => {
    load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    await apiFetch("/api/admin/admins", {
      method: "POST",
      body: JSON.stringify({ email, password, role }),
    });
    setEmail("");
    setPassword("");
    load();
  };

  return (
    <div className="admin-page admin-page--admins">
      <header className="admin-page-header">
        <div>
          <h1>Администраторы</h1>
          <p className="admin-page-subtitle">Учётные записи с доступом к панели</p>
        </div>
      </header>
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
