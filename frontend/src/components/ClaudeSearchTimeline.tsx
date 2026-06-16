import { useEffect, useState } from "react";

type Step = "searching" | "reading" | "composing";

type Props = {
  query: string | null;
  step: Step;
  visible: boolean;
};

const STEP_LABELS: Record<Step, string> = {
  searching: "Ищу в интернете",
  reading: "Читаю найденные страницы",
  composing: "Формирую ответ",
};

const STEP_ORDER: Step[] = ["searching", "reading", "composing"];

export function ClaudeSearchTimeline({ query, step, visible }: Props) {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    if (!visible) return;
    const id = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "." : d + "."));
    }, 500);
    return () => clearInterval(id);
  }, [visible]);

  if (!visible) return null;

  const currentIdx = STEP_ORDER.indexOf(step);

  return (
    <div className="claude-search-timeline" aria-live="polite" aria-label="Поиск Claude">
      {query && (
        <div className="claude-search-query">
          <span className="claude-search-query-icon">🔍</span>
          <span className="claude-search-query-text">{query}</span>
        </div>
      )}
      <div className="claude-search-steps">
        {STEP_ORDER.map((s, i) => {
          const isDone = i < currentIdx;
          const isActive = i === currentIdx;
          return (
            <div
              key={s}
              className={`claude-search-step${isDone ? " claude-search-step--done" : ""}${isActive ? " claude-search-step--active" : ""}`}
            >
              <span className="claude-search-step-icon" aria-hidden>
                {isDone ? "✓" : isActive ? "⟳" : "○"}
              </span>
              <span className="claude-search-step-label">
                {STEP_LABELS[s]}
                {isActive && <span className="claude-search-step-dots" aria-hidden>{dots}</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
