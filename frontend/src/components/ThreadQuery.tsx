import { useState } from "react";
import { t } from "../i18n";
import { useDesktopLayout } from "../hooks/useDesktopLayout";

type Props = {
  query: string;
};

export function ThreadQuery({ query }: Props) {
  const isDesktop = useDesktopLayout();
  const [copied, setCopied] = useState(false);

  const copyQuery = async () => {
    if (!query.trim()) return;
    try {
      await navigator.clipboard.writeText(query);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  if (isDesktop) {
    return (
      <div className="thread-query">
        <p className="thread-query-text">{query}</p>
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`thread-query thread-query--mobile${copied ? " thread-query--copied" : ""}`}
      onClick={() => void copyQuery()}
      aria-label={`${t("queryLabel")}. ${copied ? t("copied") : t("copyAnswer")}`}
    >
      <span className="thread-query-text">{query}</span>
      <span className="thread-query-copy-action">{copied ? t("copied") : t("copyAnswer")}</span>
    </button>
  );
}
