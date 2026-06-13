import { useState } from "react";
import { Share2, Copy } from "lucide-react";
import type { GeneratedDocumentInfo, MessageFeedback, Source } from "../api/client";
import { shareGeneratedDocument } from "./GeneratedDocumentCard";
import { answerHasText } from "../lib/answerText";
import { formatAnswerForDisplay } from "../lib/formatAnswer";
import { buildCopyText, isProPlan } from "../lib/copyAttribution";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import { AnswerFeedback } from "./AnswerFeedback";
import { SourcesPanel } from "./SourcesPanel";
import { SourcesTriggerButton } from "./SourcesTriggerButton";

type Props = {
  answer: string;
  title?: string;
  sources: Source[];
  messageId?: string;
  token?: string | null;
  userFeedback?: MessageFeedback | null;
  generatedDocument?: GeneratedDocumentInfo | null;
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function AnswerFooter({
  answer,
  title,
  sources,
  messageId,
  token,
  userFeedback,
  generatedDocument,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);

  if (!answerHasText(answer)) return null;

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
    if (generatedDocument?.id) {
      await shareGeneratedDocument(generatedDocument, token ?? null, isPro);
      return;
    }
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
        </div>

        {hasSources && (
          <div className="answer-footer-sources">
            <SourcesTriggerButton sources={sources} onClick={() => setSourcesOpen(true)} />
          </div>
        )}
      </div>

      {hasSources && (
        <SourcesPanel
          open={sourcesOpen}
          query={title}
          sources={sources}
          onClose={() => setSourcesOpen(false)}
        />
      )}
    </div>
  );
}

function ShareIcon() {
  return <Share2 width={18} height={18} strokeWidth={1.8} aria-hidden />;
}

function CopyIcon() {
  return <Copy width={18} height={18} strokeWidth={1.8} aria-hidden />;
}
