import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function AgentMaxLinkModal({ open, onClose }: Props) {
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
        aria-labelledby="agent-max-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="agent-max-modal-title" className="feedback-modal-title">
          {t("agentMaxModalTitle")}
        </h2>
        <p className="pro-upgrade-modal-description">{t("agentMaxModalDescription")}</p>
        <div className="feedback-modal-actions pro-upgrade-modal-actions">
          <Link to="/profile" className="btn-primary btn-block" onClick={onClose}>
            {t("agentMaxModalCta")}
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
