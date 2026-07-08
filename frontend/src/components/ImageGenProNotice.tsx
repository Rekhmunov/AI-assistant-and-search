import { Link } from "react-router-dom";
import { t } from "../i18n";

export function ImageGenProNotice() {
  return (
    <div className="guest-limit-notice free-limit-notice" role="alert">
      <p className="guest-limit-notice-text">
        {t("imageGenProIntro")}{" "}
        <Link to="/profile" className="guest-limit-notice-link">
          {t("upgradePro")}
        </Link>
        .
      </p>
    </div>
  );
}
