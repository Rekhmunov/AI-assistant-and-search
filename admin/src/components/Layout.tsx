import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../AuthContext";

const NAV: { to: string; label: string; perm: string }[] = [
  { to: "/", label: "Дашборд", perm: "dashboard:read" },
  { to: "/broadcasts", label: "Рассылки", perm: "broadcasts:read" },
  { to: "/users", label: "Пользователи", perm: "users:read" },
  { to: "/payments", label: "Платежи", perm: "payments:read" },
  { to: "/settings", label: "Настройки", perm: "settings:read" },
  { to: "/audit", label: "Аудит", perm: "audit:read" },
  { to: "/admins", label: "Админы", perm: "admins:read" },
];

export function Layout() {
  const { admin, logout, can } = useAuth();

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">AI Search Admin</div>
        <nav>
          {NAV.filter((n) => can(n.perm)).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-meta">
            {admin?.email}
            <span className="role">{admin?.role}</span>
          </div>
          <button type="button" className="btn-secondary" onClick={() => logout()}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
