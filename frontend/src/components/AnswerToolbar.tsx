import { useState } from "react";
import { t } from "../i18n";

type Props = {
  answer: string;
  title?: string;
};

export function AnswerToolbar({ answer, title }: Props) {
  const [copied, setCopied] = useState(false);

  if (!answer.trim()) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  const share = async () => {
    const payload = { title: title || "Glosix", text: answer };
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
    <div className="answer-toolbar">
      <button
        type="button"
        className="answer-toolbar-btn answer-toolbar-btn-icon"
        onClick={share}
        aria-label={t("share")}
        title={t("share")}
      >
        <ShareIcon />
      </button>
      <button
        type="button"
        className="answer-toolbar-btn answer-toolbar-btn-icon"
        onClick={copy}
        aria-label={copied ? t("copied") : t("copyAnswer")}
        title={copied ? t("copied") : t("copyAnswer")}
      >
        <CopyIcon />
      </button>
    </div>
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
