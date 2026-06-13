import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bell, ChevronRight } from "lucide-react";
import { createAgentThreadWithTemplate } from "../api/client";
import { MobilePageHeader } from "../components/MobilePageHeader";
import { MobileNewThreadButton } from "../components/MobileNewThreadButton";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useAuthStore } from "../store/authStore";
import { t } from "../i18n";

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
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isDesktop = useDesktopLayout();

  const isPro = user?.plan === "pro";

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
    <div className={`page page-agents${isDesktop ? "" : " page-agents--mobile"}`}>
      {isDesktop ? (
        <div className="agents-page-header">
          <h1 className="agents-page-title">{t("navAgents")}</h1>
          <p className="agents-page-sub">
            Автоматизация в MAX: напоминания, дайджесты, модерация, ИИ-помощник
          </p>
        </div>
      ) : (
        <MobilePageHeader
          variant="agents"
          title={t("navAgents")}
        />
      )}

      {isDesktop ? (
        <>
          {!isPro ? (
            <div className="agents-pro-gate">
              <div className="agents-pro-gate-icon">🤖</div>
              <p className="agents-pro-gate-title">Агенты доступны в тарифе Pro</p>
              <p className="agents-pro-gate-sub">Подключите Pro чтобы автоматизировать задачи в MAX</p>
              <button className="btn-primary" onClick={() => navigate("/profile")}>Перейти в Pro</button>
            </div>
          ) : (
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
          )}
        </>
      ) : (
        <>
          <div className="agents-scroll">
            {!isPro ? (
              <div className="agents-pro-gate">
                <div className="agents-pro-gate-icon">🤖</div>
                <p className="agents-pro-gate-title">Агенты доступны в тарифе Pro</p>
                <p className="agents-pro-gate-sub">Подключите Pro чтобы автоматизировать задачи в MAX</p>
                <button className="btn-primary" onClick={() => navigate("/profile")}>Перейти в Pro</button>
              </div>
            ) : (
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
            )}
          </div>
          <div className="mobile-new-thread-bar mobile-new-thread-bar--docked">
            <MobileNewThreadButton variant="labeled" onClick={() => navigate("/")} />
          </div>
        </>
      )}
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
