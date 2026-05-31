import { Link } from "react-router-dom";
import { ThreadTabsBar, type ThreadTab } from "./ThreadTabsBar";
import { t } from "../i18n";
import { ProfileIcon } from "./MobileNavIcons";

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
