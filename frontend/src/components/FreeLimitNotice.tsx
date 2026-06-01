import { Link } from "react-router-dom";
import { t } from "../i18n";

export function FreeLimitNotice() {
  return (
    <div className="guest-limit-notice free-limit-notice" role="alert">
      <p className="guest-limit-notice-text">
        {t("freeSearchLimitIntro")}{" "}
        {t("freeSearchLimitProHint")}{" "}
        <Link to="/profile" className="guest-limit-notice-link">
          {t("upgradePro")}
        </Link>
        .
      </p>
    </div>
  );
}
