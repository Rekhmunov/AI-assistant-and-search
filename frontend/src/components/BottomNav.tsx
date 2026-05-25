import { NavLink } from "react-router-dom";
import { t } from "../i18n";

export function BottomNav() {
  return (
    <nav className="bottom-nav" aria-label={t("navMain")}>
      <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="bottom-nav-icon" aria-hidden>
          <SearchNavIcon />
        </span>
        <span className="bottom-nav-label">{t("navSearch")}</span>
      </NavLink>
      <NavLink to="/history" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="bottom-nav-icon" aria-hidden>
          <HistoryNavIcon />
        </span>
        <span className="bottom-nav-label">{t("navHistory")}</span>
      </NavLink>
      <NavLink to="/profile" className={({ isActive }) => (isActive ? "active" : "")}>
        <span className="bottom-nav-icon" aria-hidden>
          <ProfileNavIcon />
        </span>
        <span className="bottom-nav-label">{t("navProfile")}</span>
      </NavLink>
    </nav>
  );
}

function SearchNavIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M16 16l5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function HistoryNavIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
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
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
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
