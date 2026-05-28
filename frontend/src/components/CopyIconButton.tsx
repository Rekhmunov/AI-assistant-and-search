import { useState } from "react";
import { buildCopyText, isProPlan } from "../lib/copyAttribution";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type Props = {
  text: string;
  className?: string;
};

export function CopyIconButton({ text, className = "answer-icon-btn" }: Props) {
  const [copied, setCopied] = useState(false);
  const plan = useAuthStore((s) => s.user?.plan);
  const isPro = isProPlan(plan);

  const copy = async () => {
    if (!text) return;
    const payload = buildCopyText(text, isPro);
    if (!payload) return;
    try {
      await navigator.clipboard.writeText(payload);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <button
      type="button"
      className={className}
      onClick={() => void copy()}
      aria-label={copied ? t("copied") : t("copyAnswer")}
      title={copied ? t("copied") : t("copyAnswer")}
    >
      <CopyIcon />
    </button>
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
