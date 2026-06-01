import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { MessageFeedback } from "../api/client";
import { submitMessageFeedback, type FeedbackReasonCode } from "../api/client";
import { useBodyScrollLock } from "../hooks/useBodyScrollLock";
import { t } from "../i18n";

const THANK_YOU_MS = 4500;

const DOWN_REASONS: { code: FeedbackReasonCode; labelKey: string }[] = [
  { code: "outdated", labelKey: "feedbackReasonOutdated" },
  { code: "inaccurate", labelKey: "feedbackReasonInaccurate" },
  { code: "wrong_sources", labelKey: "feedbackReasonWrongSources" },
  { code: "other", labelKey: "feedbackReasonOther" },
];

type Props = {
  messageId: string;
  token: string | null;
  initialFeedback?: MessageFeedback | null;
};

export function AnswerFeedback({ messageId, token, initialFeedback }: Props) {
  const [feedback, setFeedback] = useState<MessageFeedback | null>(initialFeedback ?? null);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedReason, setSelectedReason] = useState<FeedbackReasonCode | null>(null);
  const [otherText, setOtherText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [thankYouVisible, setThankYouVisible] = useState(false);
  const thankYouTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setFeedback(initialFeedback ?? null);
  }, [initialFeedback, messageId]);

  useEffect(() => {
    return () => {
      if (thankYouTimerRef.current !== null) {
        window.clearTimeout(thankYouTimerRef.current);
      }
    };
  }, []);

  const showThankYou = useCallback(() => {
    setThankYouVisible(true);
    if (thankYouTimerRef.current !== null) {
      window.clearTimeout(thankYouTimerRef.current);
    }
    thankYouTimerRef.current = window.setTimeout(() => {
      setThankYouVisible(false);
      thankYouTimerRef.current = null;
    }, THANK_YOU_MS);
  }, []);

  const submitUp = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await submitMessageFeedback(token, messageId, { rating: "up" });
      setFeedback(res.feedback);
      showThankYou();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("feedbackSubmitFailed"));
    } finally {
      setBusy(false);
    }
  };

  const submitDown = async (reason: FeedbackReasonCode, comment?: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await submitMessageFeedback(token, messageId, {
        rating: "down",
        reason_code: reason,
        comment: comment?.trim() || null,
      });
      setFeedback(res.feedback);
      setModalOpen(false);
      setSelectedReason(null);
      setOtherText("");
      showThankYou();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("feedbackSubmitFailed"));
    } finally {
      setBusy(false);
    }
  };

  const onDownClick = () => {
    setError("");
    setSelectedReason(null);
    setOtherText("");
    setModalOpen(true);
  };

  const onModalSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedReason) return;
    if (selectedReason === "other" && !otherText.trim()) {
      setError(t("feedbackCommentRequired"));
      return;
    }
    void submitDown(selectedReason, selectedReason === "other" ? otherText : undefined);
  };

  const upActive = feedback?.rating === "up";
  const downActive = feedback?.rating === "down";

  useBodyScrollLock(modalOpen);

  return (
    <>
      <button
        type="button"
        className={`answer-icon-btn answer-feedback-btn${upActive ? " answer-feedback-btn--active" : ""}`}
        onClick={() => void submitUp()}
        disabled={busy}
        aria-label={t("feedbackThumbUp")}
        title={t("feedbackThumbUp")}
        aria-pressed={upActive}
      >
        <ThumbUpIcon filled={upActive} />
      </button>
      <button
        type="button"
        className={`answer-icon-btn answer-feedback-btn${downActive ? " answer-feedback-btn--active" : ""}`}
        onClick={onDownClick}
        disabled={busy}
        aria-label={t("feedbackThumbDown")}
        title={t("feedbackThumbDown")}
        aria-pressed={downActive}
      >
        <ThumbDownIcon filled={downActive} />
      </button>

      {modalOpen &&
        createPortal(
          <div
            className="feedback-modal-overlay app-modal-overlay"
            role="presentation"
            onClick={() => !busy && setModalOpen(false)}
          >
            <div
              className="feedback-modal app-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="feedback-modal-title"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="feedback-modal-title" className="feedback-modal-title">
                {t("feedbackModalTitle")}
              </h2>
              <p className="feedback-modal-hint">{t("feedbackModalHint")}</p>
              <form onSubmit={onModalSubmit}>
                <div className="feedback-reason-list">
                  {DOWN_REASONS.map(({ code, labelKey }) => (
                    <label key={code} className="feedback-reason-option">
                      <input
                        type="radio"
                        name="feedback-reason"
                        value={code}
                        checked={selectedReason === code}
                        onChange={() => {
                          setSelectedReason(code);
                          setError("");
                        }}
                      />
                      <span>{t(labelKey)}</span>
                    </label>
                  ))}
                </div>
                {selectedReason === "other" && (
                  <label className="feedback-other-label">
                    {t("feedbackOtherLabel")}
                    <textarea
                      className="feedback-other-input"
                      rows={3}
                      value={otherText}
                      onChange={(e) => setOtherText(e.target.value)}
                      placeholder={t("feedbackOtherPlaceholder")}
                      maxLength={2000}
                    />
                  </label>
                )}
                {error && (
                  <p className="feedback-modal-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="feedback-modal-actions">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setModalOpen(false)}
                    disabled={busy}
                  >
                    {t("cancel")}
                  </button>
                  <button type="submit" className="btn-primary" disabled={busy || !selectedReason}>
                    {busy ? t("feedbackSending") : t("feedbackSend")}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
        )}

      {thankYouVisible &&
        createPortal(
          <div className="feedback-thank-toast" role="status" aria-live="polite">
            <p>{t("feedbackThankYou")}</p>
          </div>,
          document.body,
        )}
    </>
  );
}

function ThumbUpIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M7 10v12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={filled ? "currentColor" : "none"}
      />
    </svg>
  );
}

function ThumbDownIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M17 14V2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={filled ? "currentColor" : "none"}
      />
    </svg>
  );
}
