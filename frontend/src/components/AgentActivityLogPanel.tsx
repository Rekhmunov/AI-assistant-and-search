import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { fetchAgentActivityLogs, type AgentActivityLogItem } from "../api/client";
import { t } from "../i18n";

type Props = {
  threadId: string;
  token: string | null;
  /** Свернутый заголовок из сообщения в треде (опционально). */
  summaryLabel?: string;
};

export function AgentActivityLogPanel({ threadId, token, summaryLabel }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["agent-activity-logs", threadId],
    queryFn: () => fetchAgentActivityLogs(token, threadId),
    enabled: expanded && Boolean(token),
    staleTime: 15_000,
  });

  const items = data?.items ?? [];
  const label = useMemo(() => {
    if (summaryLabel) return summaryLabel;
    const count = items.length;
    return count > 0
      ? t("agentLogTitleCount", { count: String(count) })
      : t("agentLogTitle");
  }, [summaryLabel, items.length]);

  return (
    <section className="agent-log-panel">
      <button
        type="button"
        className="agent-log-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <TriangleIcon direction={expanded ? "down" : "right"} />
        <span>{label}</span>
      </button>
      {expanded ? (
        <div className="agent-log-body">
          {isLoading ? <p className="agent-log-muted">{t("agentLogLoading")}</p> : null}
          {isError ? (
            <p className="agent-log-error">
              {t("agentLogError")}{" "}
              <button type="button" className="btn-link" onClick={() => void refetch()}>
                {t("retrySearch")}
              </button>
            </p>
          ) : null}
          {!isLoading && !isError && items.length === 0 ? (
            <p className="agent-log-muted">{t("agentLogEmpty")}</p>
          ) : null}
          {items.length > 0 ? (
            <table className="agent-log-table">
              <thead>
                <tr>
                  <th>{t("agentLogColTime")}</th>
                  <th>{t("agentLogColEvent")}</th>
                  <th>{t("agentLogColDetails")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <AgentLogRow key={row.id} row={row} />
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function AgentLogRow({ row }: { row: AgentActivityLogItem }) {
  const time = new Date(row.created_at).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const detail = formatDetails(row);
  return (
    <tr className={row.level === "error" ? "agent-log-row--error" : undefined}>
      <td>{time}</td>
      <td>{row.event}</td>
      <td>{detail}</td>
    </tr>
  );
}

function formatDetails(row: AgentActivityLogItem): string {
  const d = row.details ?? {};
  const err = typeof d.error === "string" ? d.error : null;
  if (err) return err;
  const parts: string[] = [];
  if (typeof d.chat_id === "number") parts.push(`chat ${d.chat_id}`);
  if (typeof d.text_len === "number") parts.push(`${d.text_len} симв.`);
  if (typeof d.attachments === "number") parts.push(`${d.attachments} влож.`);
  if (typeof d.next_run_at === "string") parts.push(`след. ${d.next_run_at}`);
  if (parts.length) return parts.join(", ");
  const raw = JSON.stringify(d);
  return raw === "{}" ? "—" : raw.slice(0, 160);
}

function TriangleIcon({ direction }: { direction: "right" | "down" }) {
  if (direction === "right") {
    return <ChevronRight width={12} height={12} strokeWidth={2} aria-hidden />;
  }
  return <ChevronDown width={12} height={12} strokeWidth={2} aria-hidden />;
}

export const AGENT_LOG_MARKER = "▶ Журнал агента";

export function isAgentActivityLogContent(content: string): boolean {
  return content.trimStart().startsWith(AGENT_LOG_MARKER);
}

export function agentActivityLogSummary(content: string): string {
  const line = content.split("\n")[0]?.trim();
  return line || AGENT_LOG_MARKER;
}
