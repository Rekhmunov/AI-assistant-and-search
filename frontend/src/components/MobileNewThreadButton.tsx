import { t } from "../i18n";
import { PlusIcon } from "./MobileNavIcons";

type Props = {
  onClick: () => void;
  variant?: "icon" | "labeled";
};

export function MobileNewThreadButton({ onClick, variant = "icon" }: Props) {
  if (variant === "labeled") {
    return (
      <button
        type="button"
        className="mobile-new-search-btn"
        onClick={onClick}
        aria-label={t("newSearch")}
      >
        <span className="mobile-new-search-btn-label">{t("newSearch")}</span>
        <span className="mobile-new-search-btn-icon" aria-hidden>
          <PlusIcon />
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className="composer-new-chat"
      onClick={onClick}
      aria-label={t("newSearch")}
      title={t("newSearch")}
    >
      <PlusIcon />
    </button>
  );
}
