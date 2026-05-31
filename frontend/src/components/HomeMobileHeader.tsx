import { Link } from "react-router-dom";
import { t } from "../i18n";
import { HistoryIcon, ProfileIcon } from "./MobileNavIcons";

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
