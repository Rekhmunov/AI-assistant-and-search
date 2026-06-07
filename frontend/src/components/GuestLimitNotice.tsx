import { Link } from "react-router-dom";
import { t } from "../i18n";

export function GuestLimitNotice() {
  return (
    <div className="guest-limit-notice" role="alert">
      <p className="guest-limit-notice-text">
        {t("guestSearchLimitIntro")}{" "}
        <Link to="/login" className="guest-limit-notice-link">
          {t("guestSearchLimitRegister")}
        </Link>{" "}
        {t("guestSearchLimitSuffix")}
      </p>
    </div>
  );
}
