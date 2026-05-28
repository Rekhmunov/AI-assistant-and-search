import { useState } from "react";
import type { MessageFeedback, Source } from "../api/client";
import { formatAnswerForDisplay } from "../lib/formatAnswer";
import { buildCopyText, isProPlan } from "../lib/copyAttribution";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import { AnswerFeedback } from "./AnswerFeedback";

type Props = {
  answer: string;
  title?: string;
  sources: Source[];
  messageId?: string;
  token?: string | null;
  userFeedback?: MessageFeedback | null;
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function AnswerFooter({ answer, title, sources, messageId, token, userFeedback }: Props) {
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);

  if (!answer.trim()) return null;

  const plainAnswer = formatAnswerForDisplay(answer);
  const copyText = buildCopyText(plainAnswer, isPro);
  const hasSources = sources.length > 0;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  const share = async () => {
    const payload = { title: title || "Glosix", text: copyText };
    try {
      if (navigator.share) {
        await navigator.share(payload);
        return;
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
    }
    await copy();
  };

  return (
    <div className="answer-footer">
      <div className="answer-footer-row">
        <div className="answer-footer-icons">
          <button
            type="button"
            className="answer-icon-btn"
            onClick={share}
            aria-label={t("share")}
            title={t("share")}
          >
            <ShareIcon />
          </button>
          <button
            type="button"
            className="answer-icon-btn"
            onClick={copy}
            aria-label={copied ? t("copied") : t("copyAnswer")}
            title={copied ? t("copied") : t("copyAnswer")}
          >
            <CopyIcon />
          </button>
          {messageId && UUID_RE.test(messageId) && (
            <AnswerFeedback messageId={messageId} token={token ?? null} initialFeedback={userFeedback} />
          )}
          {hasSources && (
            <button
              type="button"
              className="sources-toggle"
              onClick={() => setSourcesOpen((v) => !v)}
              aria-expanded={sourcesOpen}
            >
              <span>{t("sources")}</span>
              <ChevronIcon open={sourcesOpen} />
            </button>
          )}
        </div>
      </div>

      {hasSources && sourcesOpen && (
        <ul className="sources-list">
          {sources.map((s) => (
            <li key={s.index} id={`source-${s.index}`}>
              <a href={s.url} target="_blank" rel="noopener noreferrer" className="sources-list-item">
                <span className="sources-list-index">[{s.index}]</span>
                <span className="sources-list-domain">{s.domain}</span>
                <span className="sources-list-title">{s.title}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={open ? "chevron-open" : ""}
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ShareIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5v9M8 9l4-4 4 4M6 19h12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}
