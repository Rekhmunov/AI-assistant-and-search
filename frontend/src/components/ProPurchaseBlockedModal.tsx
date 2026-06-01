import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function ProPurchaseBlockedModal({ open, onClose }: Props) {
  useBodyScrollLock(open);

  if (!open) return null;

  return (
    <div
      className="feedback-modal-overlay app-modal-overlay"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="feedback-modal app-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pro-purchase-blocked-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="pro-purchase-blocked-title" className="feedback-modal-title">
          {t("proPurchaseBlockedTitle")}
        </h2>
        <p className="feedback-modal-hint">{t("proPurchaseBlockedHint")}</p>
        <div className="feedback-modal-actions">
          <button type="button" className="btn-primary btn-block" onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </div>
    </div>
  );
}
