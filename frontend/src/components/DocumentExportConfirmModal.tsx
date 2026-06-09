import { createPortal } from "react-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function DocumentExportConfirmModal({ open, onClose, onConfirm }: Props) {
  useBodyScrollLock(open);
  if (!open) return null;

  return createPortal(
    <div
      className="feedback-modal-overlay app-modal-overlay"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="feedback-modal app-modal document-export-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-export-confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="document-export-confirm-title" className="feedback-modal-title">
          {t("documentExportConfirmTitle")}
        </h2>
        <p className="document-export-confirm-text">{t("documentExportConfirmText")}</p>
        <ul className="document-export-confirm-list">
          <li>{t("documentExportConfirmCheck1")}</li>
          <li>{t("documentExportConfirmCheck2")}</li>
          <li>{t("documentExportConfirmCheck3")}</li>
        </ul>
        <div className="feedback-modal-actions">
          <button type="button" className="btn-primary btn-block" onClick={onConfirm}>
            {t("documentExportConfirmProceed")}
          </button>
          <button type="button" className="btn-secondary btn-block" onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
