import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

const NAV: { to: string; label: string; perm: string }[] = [
  { to: "/", label: "Дашборд", perm: "dashboard:read" },
  { to: "/broadcasts", label: "Рассылки", perm: "broadcasts:read" },
  { to: "/users", label: "Пользователи", perm: "users:read" },
  { to: "/payments", label: "Платежи", perm: "payments:read" },
  { to: "/settings", label: "Настройки", perm: "settings:read" },
  { to: "/agents", label: "Агенты", perm: "settings:read" },
  { to: "/documents", label: "Документы", perm: "legal:read" },
  { to: "/blog", label: "Блог", perm: "blog:read" },
  { to: "/support", label: "Тикеты", perm: "support:read" },
  { to: "/audit", label: "Аудит", perm: "audit:read" },
  { to: "/admins", label: "Админы", perm: "admins:read" },
];

function MenuIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 7h16M4 12h16M4 17h16"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Layout() {
  const { admin, logout, can } = useAuth();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [openTicketCount, setOpenTicketCount] = useState(0);
  const showSupportBadge = can("support:read");

  const visibleNav = NAV.filter((n) => can(n.perm));

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [navOpen]);

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

  const navLinks = visibleNav.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.to === "/"}
      className={({ isActive }) => (isActive ? "active" : undefined)}
      onClick={() => setNavOpen(false)}
    >
      <span className="admin-sidebar-nav-label">{item.label}</span>
      {item.to === "/support" && openTicketCount > 0 && (
        <span className="admin-sidebar-nav-badge" aria-label={`Новых тикетов: ${openTicketCount}`}>
          {openTicketCount > 99 ? "99+" : openTicketCount}
        </span>
      )}
    </NavLink>
  ));

  return (
    <div className={`admin-shell${navOpen ? " admin-shell--nav-open" : ""}`}>
      <header className="admin-mobile-header">
        <button
          type="button"
          className="admin-mobile-menu-btn"
          aria-label="Открыть меню"
          aria-expanded={navOpen}
          onClick={() => setNavOpen(true)}
        >
          <MenuIcon />
        </button>
        <div className="admin-mobile-brand">
          <span className="glosix-wordmark glosix-wordmark--mobile">Glosix</span>
          <span className="admin-sidebar-badge">Admin</span>
        </div>
        {showSupportBadge && openTicketCount > 0 && (
          <span className="admin-mobile-ticket-badge" aria-label={`Новых тикетов: ${openTicketCount}`}>
            {openTicketCount > 99 ? "99+" : openTicketCount}
          </span>
        )}
      </header>

      <button
        type="button"
        className="admin-sidebar-overlay"
        aria-label="Закрыть меню"
        tabIndex={navOpen ? 0 : -1}
        onClick={() => setNavOpen(false)}
      />

      <aside className={`admin-sidebar${navOpen ? " admin-sidebar--open" : ""}`}>
        <div className="admin-sidebar-top">
          <div className="admin-sidebar-brand">
            <span className="glosix-wordmark glosix-wordmark--sidebar">Glosix</span>
            <span className="admin-sidebar-badge">Admin</span>
          </div>
          <button
            type="button"
            className="admin-sidebar-close"
            aria-label="Закрыть меню"
            onClick={() => setNavOpen(false)}
          >
            <CloseIcon />
          </button>
        </div>
        <nav className="admin-sidebar-nav" aria-label="Разделы админки">
          {navLinks}
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
