import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";
import { ProBenefitsList } from "./ProBenefitsList";

type Props = {
  open: boolean;
  onClose: () => void;
  title?: string;
};

export function ProUpgradeModal({
  open,
  onClose,
  title = t("proUpgradeModalTitle"),
}: Props) {
  useBodyScrollLock(open);

  if (!open) return null;

  return createPortal(
    <div
      className="feedback-modal-overlay app-modal-overlay pro-upgrade-modal-overlay"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="feedback-modal app-modal pro-upgrade-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pro-upgrade-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="pro-upgrade-modal-title" className="feedback-modal-title">
          {title}
        </h2>
        <ProBenefitsList className="profile-pro-benefits-list pro-upgrade-modal-benefits" />
        <div className="feedback-modal-actions pro-upgrade-modal-actions">
          <Link to="/profile" className="btn-primary btn-block" onClick={onClose}>
            {t("upgradePro")}
          </Link>
          <button type="button" className="btn-secondary btn-block" onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
