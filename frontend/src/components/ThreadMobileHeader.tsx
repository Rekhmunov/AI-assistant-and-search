import { Link } from "react-router-dom";
import { ThreadTabsBar, type ThreadTab } from "./ThreadTabsBar";
import { t } from "../i18n";
import { BackIcon, ProfileIcon } from "./MobileNavIcons";

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

      {/* Only show tab switcher when there are multiple tabs to choose from */}
      {showImagesTab && (
        <ThreadTabsBar
          variant="segment"
          activeTab={activeTab}
          onTabChange={onTabChange}
          showImagesTab={showImagesTab}
          totalImages={totalImages}
        />
      )}

      <div className="thread-mobile-header-side thread-mobile-header-side--right" aria-hidden />
    </header>
  );
}
