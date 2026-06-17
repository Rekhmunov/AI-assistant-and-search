import { useEffect, useRef, useState } from "react";
import { Clock, ChevronDown } from "lucide-react";
import type { AgentThinkingEvent } from "../api/client";

interface Props {
  events: AgentThinkingEvent[];
  isActive: boolean;
}

function toolIcon(tool: string): string {
  if (tool.startsWith("max_send")) return "📤";
  if (tool.startsWith("max_probe") || tool.startsWith("max_get")) return "🔍";
  if (tool.startsWith("max_list")) return "📋";
  if (tool.startsWith("max_resolve")) return "🔗";
  if (tool.startsWith("max_read")) return "📖";
  if (tool === "web_search") return "🌐";
  if (tool === "read_knowledge_base") return "📄";
  if (tool === "update_agent_memory") return "💾";
  if (tool.startsWith("store_") || tool.startsWith("query_")) return "🗃️";
  return "🔧";
}

function formatArguments(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 0)
      .replace(/^\{/, "")
      .replace(/\}$/, "")
      .replace(/"([^"]+)":/g, "$1:")
      .trim();
  } catch {
    return "";
  }
}

export function AgentThinkingPanel({ events, isActive }: Props) {
  // Раскрыт пока агент активен; сворачивается автоматически после завершения
  const [expanded, setExpanded] = useState(true);
  const [manualOverride, setManualOverride] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Сворачиваем когда агент завершил ответ (если пользователь не открыл вручную)
  useEffect(() => {
    if (!isActive && !manualOverride) {
      setExpanded(false);
    }
    if (isActive) {
      // Новый запрос — снимаем ручной оверрайд и раскрываем
      setManualOverride(false);
      setExpanded(true);
    }
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleToggle = () => {
    setManualOverride(true);
    setExpanded((v) => !v);
  };

  // Автоскролл вниз при новых событиях
  useEffect(() => {
    if (expanded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, expanded]);

  if (events.length === 0) return null;

  return (
    <div className="agent-thinking-panel">
      <button
        className="agent-thinking-toggle"
        onClick={handleToggle}
        aria-expanded={expanded}
      >
        <span className="agent-thinking-icon">
          {isActive ? (
            <span className="agent-thinking-spinner" aria-hidden />
          ) : (
            <Clock size={13} strokeWidth={2} aria-hidden />
          )}
        </span>
        <span className="agent-thinking-label">Процесс размышлений</span>
        <ChevronDown
          size={13}
          strokeWidth={2}
          className={`agent-thinking-chevron${expanded ? " agent-thinking-chevron--open" : ""}`}
          aria-hidden
        />
      </button>

      {expanded && (
        <div className="agent-thinking-body" ref={scrollRef}>
          {events.map((ev, i) => {
            if (ev.type === "thinking") {
              return (
                <div key={i} className="agent-thinking-item agent-thinking-item--plan">
                  <span className="agent-thinking-item-icon">💭</span>
                  <span className="agent-thinking-item-text">{ev.text}</span>
                </div>
              );
            }
            if (ev.type === "tool_call") {
              const argsStr = formatArguments(ev.arguments);
              return (
                <div key={i} className="agent-thinking-item agent-thinking-item--tool-call">
                  <span className="agent-thinking-item-icon">{toolIcon(ev.tool)}</span>
                  <span className="agent-thinking-item-text">
                    <span className="agent-thinking-tool-name">{ev.tool}</span>
                    {argsStr && (
                      <span className="agent-thinking-tool-args">({argsStr})</span>
                    )}
                  </span>
                </div>
              );
            }
            if (ev.type === "tool_result") {
              return (
                <div
                  key={i}
                  className={`agent-thinking-item agent-thinking-item--tool-result${ev.ok ? "" : " agent-thinking-item--error"}`}
                >
                  <span className="agent-thinking-item-icon">{ev.ok ? "✓" : "✗"}</span>
                  <span className="agent-thinking-item-text">{ev.summary}</span>
                </div>
              );
            }
            return null;
          })}
        </div>
      )}
    </div>
  );
}
