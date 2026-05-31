import { Link } from "react-router-dom";
import { ThreadTabsBar, type ThreadTab } from "./ThreadTabsBar";
import { t } from "../i18n";

type Props = {
  onBack: () => void;
  activeTab: ThreadTab;
  onTabChange: (tab: ThreadTab) => void;
  showImagesTab: boolean;
  totalImages: number;
};

export function ThreadMobileHeader({
  onBack,
  activeTab,
  onTabChange,
  showImagesTab,
  totalImages,
}: Props) {
  return (
    <header className="thread-mobile-header">
      <div className="thread-mobile-header-side thread-mobile-header-side--left">
        <button
          type="button"
          className="thread-header-icon-btn"
          onClick={onBack}
          aria-label={t("back")}
          title={t("back")}
        >
          <BackIcon />
        </button>
        <Link to="/profile" className="thread-header-icon-btn" aria-label={t("navProfile")} title={t("navProfile")}>
          <ProfileIcon />
        </Link>
      </div>

      <ThreadTabsBar
        variant="segment"
        activeTab={activeTab}
        onTabChange={onTabChange}
        showImagesTab={showImagesTab}
        totalImages={totalImages}
      />

      <div className="thread-mobile-header-side thread-mobile-header-side--right" aria-hidden />
    </header>
  );
}

function BackIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 6l-6 6 6 6"
        stroke="currentColor"
        strokeWidth="2"
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
