import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { t } from "../i18n";

function SearchNavIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function HistoryNavIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 8v5l3 2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3.5 12a8.5 8.5 0 101.2-4.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M3 7v5h5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ProfileNavIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5 20c0-3.5 3.1-6 7-6s7 2.5 7 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function NavItem({
  to,
  end,
  label,
  icon,
}: {
  to: string;
  end?: boolean;
  label: string;
  icon: ReactNode;
}) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => (isActive ? "active" : "")}>
      <span className="app-nav-icon" aria-hidden>
        {icon}
      </span>
      <span className="app-nav-label">{label}</span>
    </NavLink>
  );
}

export function AppNavigation() {
  const aria = t("navMain");

  return (
    <>
      <nav className="sidebar-nav" aria-label={aria}>
        <Link to="/" className="sidebar-brand" aria-label="Glosix">
          <img src="/glosix-logo.svg" alt="" className="glosix-logo" />
        </Link>
        <div className="sidebar-nav-top">
          <NavItem to="/" end label={t("navSearch")} icon={<SearchNavIcon />} />
          <NavItem to="/history" label={t("navHistory")} icon={<HistoryNavIcon />} />
        </div>
        <div className="sidebar-nav-bottom">
          <NavItem to="/profile" label={t("navProfile")} icon={<ProfileNavIcon />} />
        </div>
      </nav>

      <nav className="bottom-nav" aria-label={aria}>
        <NavItem to="/" end label={t("navSearch")} icon={<SearchNavIcon />} />
        <NavItem to="/history" label={t("navHistory")} icon={<HistoryNavIcon />} />
        <NavItem to="/profile" label={t("navProfile")} icon={<ProfileNavIcon />} />
      </nav>
    </>
  );
}
