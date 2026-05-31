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
          <AnswerTabIcon />
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
            <ImagesTabIcon />
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

function AnswerTabIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3zM5 17l.8 2.4L8 20l-2.2.6L5 23l-.8-2.4L2 20l2.2-.6L5 17zm14 0l.8 2.4L22 20l-2.2.6L19 23l-.8-2.4L16 20l2.2-.6L19 17z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ImagesTabIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M8 11l2.5 2.5L14 10l4 5H6l2-4z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="9" cy="9" r="1.2" fill="currentColor" />
    </svg>
  );
}
