import { PRO_BENEFIT_KEYS } from "../constants/proBenefits";
import { t } from "../i18n";

type Props = {
  className?: string;
};

export function ProBenefitsList({ className = "profile-pro-benefits-list" }: Props) {
  return (
    <ul className={className}>
      {PRO_BENEFIT_KEYS.map((key) => (
        <li key={key} className="profile-pro-benefit-item">
          <span className="profile-pro-benefit-icon" aria-hidden>
            ✓
          </span>
          <span>{t(key)}</span>
        </li>
      ))}
    </ul>
  );
}
