import { Link } from "react-router-dom";
import { t } from "../i18n";

export function HomeMobileHeader() {
  return (
    <header className="thread-mobile-header home-mobile-header">
      <div className="thread-mobile-header-side thread-mobile-header-side--left">
        <Link
          to="/history"
          className="thread-header-icon-btn"
          aria-label={t("navHistory")}
          title={t("navHistory")}
        >
          <HistoryIcon />
        </Link>
        <Link
          to="/profile"
          className="thread-header-icon-btn"
          aria-label={t("navProfile")}
          title={t("navProfile")}
        >
          <ProfileIcon />
        </Link>
      </div>
      <div className="thread-mobile-header-spacer" aria-hidden />
      <div className="thread-mobile-header-side thread-mobile-header-side--right" aria-hidden />
    </header>
  );
}

function HistoryIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
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

function ProfileIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
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
