import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { MessageFeedback } from "../api/client";
import { submitMessageFeedback, type FeedbackReasonCode } from "../api/client";
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
    if (!token || busy) return;
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
    if (!token || busy) return;
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

  return (
    <>
      <button
        type="button"
        className={`answer-icon-btn answer-feedback-btn${upActive ? " answer-feedback-btn--active" : ""}`}
        onClick={() => void submitUp()}
        disabled={busy || !token}
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
        disabled={busy || !token}
        aria-label={t("feedbackThumbDown")}
        title={t("feedbackThumbDown")}
        aria-pressed={downActive}
      >
        <ThumbDownIcon filled={downActive} />
      </button>

      {modalOpen && (
        <div
          className="feedback-modal-overlay"
          role="presentation"
          onClick={() => !busy && setModalOpen(false)}
        >
          <div
            className="feedback-modal"
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
        </div>
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
        d="M7 11v10H4V11h3zm3.5-8a2 2 0 012 1.73l1.06 2.12 2.33.34a2 2 0 011.1 3.41l-1.69 1.64.4 2.32a2 2 0 01-2.9 2.11L12 15.9l-2.08 1.09a2 2 0 01-2.9-2.11l.4-2.32-1.69-1.64a2 2 0 011.1-3.41l2.33-.34L9.5 4.73A2 2 0 0112 3z"
        stroke="currentColor"
        strokeWidth="1.6"
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
        d="M7 3v10H4V3h3zm3.5 14a2 2 0 01-2-1.73L7.44 13.15l-2.33-.34a2 2 0 01-1.1-3.41l1.69-1.64-.4-2.32a2 2 0 012.9-2.11L12 8.1l2.08-1.09a2 2 0 012.9 2.11l-.4 2.32 1.69 1.64a2 2 0 01-1.1 3.41l-2.33.34-1.06 2.12A2 2 0 0112 21z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        fill={filled ? "currentColor" : "none"}
      />
    </svg>
  );
}
