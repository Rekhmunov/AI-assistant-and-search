import { t } from "../i18n";

export type ThreadTab = "answer" | "images";

type Props = {
  activeTab: ThreadTab;
  onTabChange: (tab: ThreadTab) => void;
  showImagesTab: boolean;
  totalImages: number;
  /** Компактный pill в шапке mobile-треда */
  variant?: "bar" | "segment";
};

export function ThreadTabsBar({
  activeTab,
  onTabChange,
  showImagesTab,
  totalImages,
  variant = "bar",
}: Props) {
  if (variant === "segment") {
    return (
      <div
        className="thread-tabs-segment"
        role="tablist"
        aria-label={t("turnContentTabs")}
      >
        <button
          type="button"
          role="tab"
          id="thread-tab-answer"
          aria-selected={activeTab === "answer"}
          aria-controls="thread-panel-answer"
          className={`thread-tabs-segment-btn${activeTab === "answer" ? " thread-tabs-segment-btn--active" : ""}`}
          onClick={() => onTabChange("answer")}
          title={t("turnTabAnswer")}
        >
          <AnswerTabIcon large />
        </button>

        {showImagesTab && (
          <button
            type="button"
            role="tab"
            id="thread-tab-images"
            aria-selected={activeTab === "images"}
            aria-controls="thread-panel-images"
            className={`thread-tabs-segment-btn${activeTab === "images" ? " thread-tabs-segment-btn--active" : ""}`}
            onClick={() => onTabChange("images")}
            title={t("turnTabImages")}
          >
            <ImagesTabIcon large />
            {totalImages > 0 && (
              <span className="thread-tabs-segment-badge">{totalImages}</span>
            )}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="thread-tabs-bar" role="tablist" aria-label={t("turnContentTabs")}>
      <button
        type="button"
        role="tab"
        id="thread-tab-answer"
        aria-selected={activeTab === "answer"}
        aria-controls="thread-panel-answer"
        className={`thread-tab${activeTab === "answer" ? " thread-tab--active" : ""}`}
        onClick={() => onTabChange("answer")}
      >
        <AnswerTabIcon />
        <span>{t("turnTabAnswer")}</span>
      </button>

      {showImagesTab && (
        <button
          type="button"
          role="tab"
          id="thread-tab-images"
          aria-selected={activeTab === "images"}
          aria-controls="thread-panel-images"
          className={`thread-tab${activeTab === "images" ? " thread-tab--active" : ""}`}
          onClick={() => onTabChange("images")}
        >
          <ImagesTabIcon />
          <span>{t("turnTabImages")}</span>
          {totalImages > 0 && <span className="thread-tab-badge">{totalImages}</span>}
        </button>
      )}
    </div>
  );
}

function AnswerTabIcon({ large }: { large?: boolean }) {
  const size = large ? 22 : 16;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 5h12a2 2 0 012 2v8a2 2 0 01-2 2H10l-4 3v-3H6a2 2 0 01-2-2V7a2 2 0 012-2z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M8 9h8M8 12.5h5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function ImagesTabIcon({ large }: { large?: boolean }) {
  const size = large ? 22 : 16;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="8.5" cy="10" r="1.6" fill="currentColor" />
      <path
        d="M3 16l4.5-4 3.5 3 2.5-2L21 16"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
