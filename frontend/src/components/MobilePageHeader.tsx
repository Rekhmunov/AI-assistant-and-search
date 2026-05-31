import { Link } from "react-router-dom";
import { t } from "../i18n";
import { HistoryIcon, NewChatIcon, ProfileIcon, SearchIcon } from "./MobileNavIcons";

type Props = {
  variant: "profile" | "history";
  title: string;
  historySearchActive?: boolean;
  onHistorySearchToggle?: () => void;
};

export function MobilePageHeader({
  variant,
  title,
  historySearchActive = false,
  onHistorySearchToggle,
}: Props) {
  return (
    <header className="thread-mobile-header mobile-page-header">
      <div className="thread-mobile-header-side thread-mobile-header-side--left">
        {variant === "profile" ? (
          <>
            <Link
              to="/history"
              className="thread-header-icon-btn"
              aria-label={t("navHistory")}
              title={t("navHistory")}
            >
              <HistoryIcon />
            </Link>
            <Link
              to="/"
              className="thread-header-icon-btn"
              aria-label={t("newChat")}
              title={t("newChat")}
            >
              <NewChatIcon />
            </Link>
          </>
        ) : (
          <>
            <Link
              to="/profile"
              className="thread-header-icon-btn"
              aria-label={t("navProfile")}
              title={t("navProfile")}
            >
              <ProfileIcon />
            </Link>
            <button
              type="button"
              className={`thread-header-icon-btn${historySearchActive ? " thread-header-icon-btn--active" : ""}`}
              aria-label={t("historySearch")}
              title={t("historySearch")}
              aria-pressed={historySearchActive}
              onClick={onHistorySearchToggle}
            >
              <SearchIcon />
            </button>
          </>
        )}
      </div>
      <h1 className="mobile-page-title">{title}</h1>
      <div className="thread-mobile-header-side thread-mobile-header-side--right" aria-hidden />
    </header>
  );
}
