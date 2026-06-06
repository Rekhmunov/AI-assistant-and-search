import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

const NAV: { to: string; label: string; perm: string }[] = [
  { to: "/", label: "Дашборд", perm: "dashboard:read" },
  { to: "/broadcasts", label: "Рассылки", perm: "broadcasts:read" },
  { to: "/users", label: "Пользователи", perm: "users:read" },
  { to: "/payments", label: "Платежи", perm: "payments:read" },
  { to: "/settings", label: "Настройки", perm: "settings:read" },
  { to: "/documents", label: "Документы", perm: "legal:read" },
  { to: "/support", label: "Тикеты", perm: "support:read" },
  { to: "/audit", label: "Аудит", perm: "audit:read" },
  { to: "/admins", label: "Админы", perm: "admins:read" },
];

export function Layout() {
  const { admin, logout, can } = useAuth();
  const [openTicketCount, setOpenTicketCount] = useState(0);
  const showSupportBadge = can("support:read");

  useEffect(() => {
    if (!showSupportBadge) return;

    let cancelled = false;
    const load = async () => {
      try {
        const data = await apiFetch<{ open_count: number }>("/api/admin/support/stats");
        if (!cancelled) setOpenTicketCount(data.open_count);
      } catch {
        if (!cancelled) setOpenTicketCount(0);
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [showSupportBadge]);

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-sidebar-brand">
          <span className="glosix-wordmark glosix-wordmark--sidebar">Glosix</span>
          <span className="admin-sidebar-badge">Admin</span>
        </div>
        <nav className="admin-sidebar-nav" aria-label="Разделы админки">
          {NAV.filter((n) => can(n.perm)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              <span className="admin-sidebar-nav-label">{item.label}</span>
              {item.to === "/support" && openTicketCount > 0 && (
                <span className="admin-sidebar-nav-badge" aria-label={`Новых тикетов: ${openTicketCount}`}>
                  {openTicketCount > 99 ? "99+" : openTicketCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="admin-sidebar-footer">
          <div className="user-meta">
            <span className="user-meta-email">{admin?.email}</span>
            <span className="role">{admin?.role}</span>
          </div>
          <button type="button" className="btn-secondary btn-secondary--block" onClick={() => logout()}>
            Выйти
          </button>
        </div>
      </aside>
      <main className="admin-content">
        <Outlet />
      </main>
    </div>
  );
}
