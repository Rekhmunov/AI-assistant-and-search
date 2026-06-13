import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bell, ChevronRight } from "lucide-react";
import { createAgentThreadWithTemplate } from "../api/client";
import { useAuthStore } from "../store/authStore";

interface AgentTemplate {
  id: string;
  title: string;
  description: string;
  badges: string[];
  icon: React.ReactNode;
  color: string;
}

const AGENT_TEMPLATES: AgentTemplate[] = [
  {
    id: "reminder",
    title: "Напоминания",
    description: "Отправляй себе или в группу в нужное время",
    badges: ["Разовые", "По расписанию", "Личка и группы"],
    icon: <Bell size={26} strokeWidth={1.8} />,
    color: "#20808d",
  },
];

export function AgentsPage() {
  const token = useAuthStore((s) => s.token);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const createAgent = useMutation({
    mutationFn: (templateId: string) => createAgentThreadWithTemplate(token, templateId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      navigate(`/thread/${result.thread.id}`, {
        state: { agentRevealWelcome: true },
      });
    },
  });

  return (
    <div className="page page-agents">
      <div className="agents-page-header">
        <h1 className="agents-page-title">Агенты</h1>
        <p className="agents-page-sub">
          Автоматизация в MAX: напоминания, дайджесты, модерация, ИИ-помощник
        </p>
      </div>

      <div className="agents-catalog">
        {AGENT_TEMPLATES.map((tmpl) => (
          <AgentTemplateCard
            key={tmpl.id}
            template={tmpl}
            loading={createAgent.isPending && createAgent.variables === tmpl.id}
            onClick={() => createAgent.mutate(tmpl.id)}
          />
        ))}
      </div>
    </div>
  );
}

function AgentTemplateCard({
  template,
  loading,
  onClick,
}: {
  template: AgentTemplate;
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="agent-tmpl-card"
      onClick={onClick}
      disabled={loading}
      style={{ "--agent-color": template.color } as React.CSSProperties}
    >
      <div className="agent-tmpl-card__icon-wrap">
        {template.icon}
      </div>
      <div className="agent-tmpl-card__body">
        <span className="agent-tmpl-card__title">{template.title}</span>
        <span className="agent-tmpl-card__desc">{template.description}</span>
        <div className="agent-tmpl-card__badges">
          {template.badges.map((b) => (
            <span key={b} className="agent-tmpl-card__badge">{b}</span>
          ))}
        </div>
      </div>
      <div className="agent-tmpl-card__arrow">
        {loading ? (
          <span className="agent-tmpl-card__spinner" />
        ) : (
          <ChevronRight size={18} strokeWidth={1.8} />
        )}
      </div>
    </button>
  );
}
