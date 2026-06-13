import { useState } from "react";
import { Share2, Copy } from "lucide-react";
import { answerHasText } from "../lib/answerText";
import { formatAnswerForDisplay } from "../lib/formatAnswer";
import { buildCopyText, isProPlan } from "../lib/copyAttribution";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  answer: string;
  title?: string;
};

export function AnswerToolbar({ answer, title }: Props) {
  const [copied, setCopied] = useState(false);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);

  if (!answerHasText(answer)) return null;

  const plainAnswer = formatAnswerForDisplay(answer);
  const copyText = buildCopyText(plainAnswer, isPro);

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
  return <Share2 width={18} height={18} strokeWidth={1.8} aria-hidden />;
}

function CopyIcon() {
  return <Copy width={18} height={18} strokeWidth={1.8} aria-hidden />;
}
