import { FormEvent, useState } from "react";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (message: string) => Promise<void>;
};

export function SupportFormModal({ open, onClose, onSubmit }: Props) {
  useBodyScrollLock(open);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const text = message.trim();
    if (text.length < 3) {
      setError(t("supportFormMinLength"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit(text);
      setMessage("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("supportFormSendError"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="feedback-modal-overlay app-modal-overlay"
      role="presentation"
      onClick={busy ? undefined : onClose}
    >
      <form
        className="feedback-modal app-modal support-form-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="support-form-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => void handleSubmit(e)}
      >
        <h2 id="support-form-title" className="feedback-modal-title">
          {t("supportFormTitle")}
        </h2>
        <textarea
          className="support-form-textarea"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t("supportFormPlaceholder")}
          rows={5}
          disabled={busy}
          autoFocus
        />
        {error && <p className="feedback-modal-error">{error}</p>}
        <div className="feedback-modal-actions">
          <button type="submit" className="btn-primary btn-block" disabled={busy}>
            {busy ? "…" : t("supportFormSend")}
          </button>
          <button type="button" className="btn-secondary btn-block" disabled={busy} onClick={onClose}>
            {t("close")}
          </button>
        </div>
      </form>
    </div>
  );
}
