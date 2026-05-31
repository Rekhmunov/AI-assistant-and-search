import { useState, type ReactNode } from "react";
import type { EntityImage } from "../api/client";
import { t } from "../i18n";
import { TurnImagesTab } from "./TurnImagesTab";

export type TurnTab = "answer" | "images";

type Props = {
  query: string;
  images: EntityImage[];
  showImagesTab: boolean;
  imagesLoading?: boolean;
  children: ReactNode;
};

export function TurnContentTabs({
  query,
  images,
  showImagesTab,
  imagesLoading = false,
  children,
}: Props) {
  const [activeTab, setActiveTab] = useState<TurnTab>("answer");

  return (
    <div className="turn-content">
      <div className="turn-content-tabs" role="tablist" aria-label={t("turnContentTabs")}>
        <button
          type="button"
          role="tab"
          id="turn-tab-answer"
          aria-selected={activeTab === "answer"}
          aria-controls="turn-panel-answer"
          className={`turn-content-tab${activeTab === "answer" ? " turn-content-tab--active" : ""}`}
          onClick={() => setActiveTab("answer")}
        >
          <AnswerTabIcon />
          <span>{t("turnTabAnswer")}</span>
        </button>

        {showImagesTab && (
          <button
            type="button"
            role="tab"
            id="turn-tab-images"
            aria-selected={activeTab === "images"}
            aria-controls="turn-panel-images"
            className={`turn-content-tab${activeTab === "images" ? " turn-content-tab--active" : ""}`}
            onClick={() => setActiveTab("images")}
          >
            <ImagesTabIcon />
            <span>{t("turnTabImages")}</span>
            {images.length > 0 && (
              <span className="turn-content-tab-badge">{images.length}</span>
            )}
          </button>
        )}
      </div>

      <div className="turn-content-panels">
        <div
          id="turn-panel-answer"
          role="tabpanel"
          aria-labelledby="turn-tab-answer"
          hidden={activeTab !== "answer"}
          className="turn-content-panel"
        >
          {children}
        </div>

        {showImagesTab && (
          <div
            id="turn-panel-images"
            role="tabpanel"
            aria-labelledby="turn-tab-images"
            hidden={activeTab !== "images"}
            className="turn-content-panel"
          >
            <TurnImagesTab query={query} images={images} loading={imagesLoading} />
          </div>
        )}
      </div>
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
