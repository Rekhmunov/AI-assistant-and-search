import { useState } from "react";
import { Copy } from "lucide-react";
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
  return <Copy width={18} height={18} strokeWidth={1.8} aria-hidden />;
}
