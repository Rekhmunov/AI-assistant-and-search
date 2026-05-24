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
    <div>
      <h1>Администраторы</h1>
      {can("admins:write") && (
        <form className="card" onSubmit={create}>
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
      <table className="table">
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
              <td>{a.email}</td>
              <td>{a.role}</td>
              <td>{a.is_active ? "да" : "нет"}</td>
              <td>{a.last_login_at ? new Date(a.last_login_at).toLocaleString() : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
