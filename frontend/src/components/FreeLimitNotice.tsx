import { Link } from "react-router-dom";
import { t } from "../i18n";
import { ProBenefitsList } from "./ProBenefitsList";

export function FreeLimitNotice() {
  return (
    <div className="guest-limit-notice free-limit-notice free-limit-notice--rich" role="alert">
      <h3 className="free-limit-notice-title">{t("freeSearchLimitTitle")}</h3>
      <p className="free-limit-notice-hint">{t("freeSearchLimitHint")}</p>
      <ProBenefitsList className="profile-pro-benefits-list free-limit-notice-benefits" />
      <Link to="/profile" className="btn-primary btn-block free-limit-notice-cta">
        {t("upgradePro")}
      </Link>
    </div>
  );
}
