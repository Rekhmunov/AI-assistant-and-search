import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createAgentThread, fetchAgentList } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { t } from "../i18n";

const STATUS_LABELS: Record<string, string> = {
  active: "Активен",
  collecting: "Настройка",
  draft: "Черновик",
  paused: "Пауза",
  cancelled: "Отключён",
};

const STATUS_CLASS: Record<string, string> = {
  active: "agent-card__status--active",
  collecting: "agent-card__status--collecting",
  draft: "agent-card__status--draft",
  paused: "agent-card__status--paused",
  cancelled: "agent-card__status--cancelled",
};

const ROLE_ICONS: Record<string, string> = {
  personal_reminder: "🔔",
  group_reminder: "📢",
  group_message_log: "📋",
  news_digest: "📰",
  image_post: "🖼️",
  group_moderation: "🛡️",
  dm_assistant: "💬",
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function AgentsPage() {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["agents-list", token],
    queryFn: () => fetchAgentList(token),
    staleTime: 30_000,
  });

  const createAgent = useMutation({
    mutationFn: () => createAgentThread(token),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["agents-list"] });
      navigate(`/thread/${result.thread.id}`, {
        state: { agentRevealWelcome: true },
      });
    },
  });

  const agents = data?.agents ?? [];
  const activeAgents = agents.filter((a) => a.status === "active");
  const otherAgents = agents.filter((a) => a.status !== "active");

  return (
    <div className="page page-agents">
      <div className="agents-header">
        <div>
          <h1 className="agents-title">🤖 {t("navAgents")}</h1>
          <p className="agents-subtitle">
            Автоматизация в MAX: напоминания, дайджесты, модерация, ИИ-помощник
          </p>
        </div>
        <button
          className="btn-primary agents-create-btn"
          onClick={() => createAgent.mutate()}
          disabled={createAgent.isPending}
        >
          {createAgent.isPending ? "Создаю…" : "+ Новый агент"}
        </button>
      </div>

      {isLoading && <p className="agents-loading">Загрузка…</p>}

      {!isLoading && agents.length === 0 && (
        <div className="agents-empty">
          <div className="agents-empty-icon">🤖</div>
          <p className="agents-empty-title">Агентов пока нет</p>
          <p className="agents-empty-sub">
            Создайте агента — он будет работать в MAX автоматически
          </p>
          <button
            className="btn-primary"
            onClick={() => createAgent.mutate()}
            disabled={createAgent.isPending}
          >
            {createAgent.isPending ? "Создаю…" : "Создать первого агента"}
          </button>
        </div>
      )}

      {activeAgents.length > 0 && (
        <section className="agents-section">
          <h2 className="agents-section-title">Активные</h2>
          <div className="agents-grid">
            {activeAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onClick={() => navigate(`/thread/${agent.thread_id}`)}
              />
            ))}
          </div>
        </section>
      )}

      {otherAgents.length > 0 && (
        <section className="agents-section">
          <h2 className="agents-section-title">Остальные</h2>
          <div className="agents-grid">
            {otherAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onClick={() => navigate(`/thread/${agent.thread_id}`)}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function AgentCard({
  agent,
  onClick,
}: {
  agent: {
    id: string;
    thread_id: string;
    status: string;
    role: string | null;
    role_label: string;
    title: string;
    instruction_text: string;
    max_chat_id: number | null;
    schedule_text: string | null;
    next_run_at: string | null;
    last_dispatch_error: string | null;
  };
  onClick: () => void;
}) {
  const icon = ROLE_ICONS[agent.role ?? ""] ?? "🤖";
  const statusLabel = STATUS_LABELS[agent.status] ?? agent.status;
  const statusClass = STATUS_CLASS[agent.status] ?? "";

  return (
    <button className="agent-card" onClick={onClick}>
      <div className="agent-card__header">
        <span className="agent-card__icon">{icon}</span>
        <div className="agent-card__meta">
          <span className="agent-card__role">{agent.role_label}</span>
          <span className={`agent-card__status ${statusClass}`}>{statusLabel}</span>
        </div>
      </div>

      {agent.instruction_text && (
        <p className="agent-card__instruction">{agent.instruction_text}</p>
      )}

      <div className="agent-card__footer">
        {agent.schedule_text && (
          <span className="agent-card__detail">📅 {agent.schedule_text}</span>
        )}
        {agent.max_chat_id && (
          <span className="agent-card__detail">💬 Группа {agent.max_chat_id}</span>
        )}
        {agent.next_run_at && (
          <span className="agent-card__detail">⏰ {formatDate(agent.next_run_at)}</span>
        )}
        {agent.last_dispatch_error && (
          <span className="agent-card__detail agent-card__detail--error">⚠️ Ошибка отправки</span>
        )}
      </div>
    </button>
  );
}
