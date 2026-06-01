import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

export type ProPaymentModalState =
  | { open: false }
  | { open: true; kind: "loading" }
  | { open: true; kind: "success" }
  | { open: true; kind: "pending" | "error"; message: string; canRetry?: boolean };

type Props = {
  state: ProPaymentModalState;
  onClose: () => void;
  onRetry?: () => void;
};

export function ProPaymentStatusModal({ state, onClose, onRetry }: Props) {
  useBodyScrollLock(state.open);

  if (!state.open) return null;

  const title =
    state.kind === "loading"
      ? t("proPaymentConfirmLoadingTitle")
      : state.kind === "success"
        ? t("proPaymentConfirmSuccessTitle")
        : state.kind === "pending"
          ? t("proPaymentConfirmPendingTitle")
          : t("proPaymentConfirmErrorTitle");

  const hint =
    state.kind === "loading"
      ? t("proPaymentConfirmLoadingHint")
      : state.kind === "success"
        ? t("proPaymentConfirmSuccessHint")
        : state.kind === "pending" || state.kind === "error"
          ? state.message
          : "";

  return (
    <div
      className="feedback-modal-overlay app-modal-overlay"
      role="presentation"
      onClick={state.kind === "loading" ? undefined : onClose}
    >
      <div
        className="feedback-modal app-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pro-payment-status-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="pro-payment-status-title" className="feedback-modal-title">
          {title}
        </h2>
        {hint ? <p className="feedback-modal-hint">{hint}</p> : null}
        {state.kind === "loading" ? (
          <p className="feedback-modal-hint">{t("proPaymentConfirmPleaseWait")}</p>
        ) : null}
        <div className="feedback-modal-actions">
          {state.kind !== "loading" && (state.kind === "pending" || state.kind === "error") && state.canRetry && onRetry ? (
            <button type="button" className="btn-primary btn-block" onClick={onRetry}>
              {t("proPaymentConfirmRetry")}
            </button>
          ) : null}
          {state.kind !== "loading" ? (
            <button
              type="button"
              className={state.kind === "success" ? "btn-primary btn-block" : "btn-secondary btn-block"}
              onClick={onClose}
            >
              {t("close")}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
