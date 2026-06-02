import { t } from "../i18n";

type Props = {
  selectedCount: number;
  totalVisible: number;
  deleting: boolean;
  onSelectAll: () => void;
  onClearSelection: () => void;
  onDelete: () => void;
};

export function HistoryBulkBar({
  selectedCount,
  totalVisible,
  deleting,
  onSelectAll,
  onClearSelection,
  onDelete,
}: Props) {
  const allSelected = totalVisible > 0 && selectedCount === totalVisible;

  return (
    <div className="history-bulk-bar">
      <span className="history-bulk-count">{t("historySelectedCount", { count: selectedCount })}</span>
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
  );
}
