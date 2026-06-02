import { createPortal } from "react-dom";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  count: number;
  deleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function HistoryBulkDeleteModal({ open, count, deleting, onConfirm, onCancel }: Props) {
  useBodyScrollLock(open);

  if (!open) return null;

  return createPortal(
    <div
      className="feedback-modal-overlay app-modal-overlay"
      role="presentation"
      onClick={deleting ? undefined : onCancel}
    >
      <div
        className="feedback-modal app-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-bulk-delete-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="history-bulk-delete-title" className="feedback-modal-title">
          {t("historyBulkDeleteConfirmTitle")}
        </h2>
        <p className="feedback-modal-hint">
          {t("historyBulkDeleteConfirmHint", { count })}
        </p>
        <div className="feedback-modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={deleting}>
            {t("no")}
          </button>
          <button type="button" className="danger" onClick={onConfirm} disabled={deleting}>
            {deleting ? t("historyDeleting") : t("yes")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
