import { t } from "../i18n";

type Props = {
  selectedCount: number;
  totalVisible: number;
  deleting: boolean;
  confirmOpen: boolean;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onDelete: () => void;
  onConfirmDelete: () => void;
  onCancelConfirm: () => void;
  onExit: () => void;
};

export function HistoryBulkBar({
  selectedCount,
  totalVisible,
  deleting,
  confirmOpen,
  onSelectAll,
  onClearSelection,
  onDelete,
  onConfirmDelete,
  onCancelConfirm,
  onExit,
}: Props) {
  const allSelected = totalVisible > 0 && selectedCount === totalVisible;

  if (confirmOpen) {
    return (
      <div className="history-bulk-bar history-bulk-bar--confirm" role="dialog" aria-label={t("historyDeleteSelectedConfirm", { count: selectedCount })}>
        <p className="history-bulk-confirm-text">
          {t("historyDeleteSelectedConfirm", { count: selectedCount })}
        </p>
        <div className="history-bulk-actions">
          <button type="button" className="btn-secondary" onClick={onCancelConfirm} disabled={deleting}>
            {t("cancel")}
          </button>
          <button type="button" className="danger" onClick={onConfirmDelete} disabled={deleting}>
            {deleting ? t("historyDeleting") : t("delete")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="history-bulk-bar">
      <div className="history-bulk-meta">
        <button type="button" className="history-bulk-text-btn" onClick={onExit}>
          {t("historyCancelSelect")}
        </button>
        <span className="history-bulk-count">{t("historySelectedCount", { count: selectedCount })}</span>
      </div>
      <div className="history-bulk-actions">
        <button
          type="button"
          className="history-bulk-text-btn"
          onClick={allSelected ? onClearSelection : onSelectAll}
          disabled={totalVisible === 0}
        >
          {t("historySelectAll")}
        </button>
        <button
          type="button"
          className="danger"
          onClick={onDelete}
          disabled={selectedCount === 0 || deleting}
        >
          {t("historyDeleteSelected")}
        </button>
      </div>
    </div>
  );
}
