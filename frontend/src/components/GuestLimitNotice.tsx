import { Link } from "react-router-dom";
import { t } from "../i18n";
import { requestsPerDayLabel } from "../lib/requestsPerDayLabel";

type Props = {
  limit: number;
};

export function GuestLimitNotice({ limit }: Props) {
  const requests = requestsPerDayLabel(limit);

  return (
    <div className="guest-limit-notice" role="alert">
      <p className="guest-limit-notice-text">
        {t("guestSearchLimitIntro", { requests })}{" "}
        {t("guestSearchLimitRegisterHint")}{" "}
        <Link to="/login" className="guest-limit-notice-link">
          {t("register")}
        </Link>
        .
      </p>
    </div>
  );
}
