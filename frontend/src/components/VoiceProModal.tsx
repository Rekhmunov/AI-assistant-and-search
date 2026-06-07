import { Link } from "react-router-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function VoiceProModal({ open, onClose }: Props) {
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
        aria-labelledby="voice-pro-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="voice-pro-modal-title" className="feedback-modal-title">
          {t("voiceProModalTitle")}
        </h2>
        <p className="feedback-modal-hint">{t("voiceProModalHint")}</p>
        <div className="feedback-modal-actions voice-pro-modal-actions">
          <Link to="/profile" className="btn-primary btn-block" onClick={onClose}>
            {t("upgradePro")}
          </Link>
          <button type="button" className="btn-secondary btn-block" onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </div>
    </div>
  );
}
