import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { fetchThreads } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

function dayLabel(date: Date): string {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startYesterday = new Date(startToday);
  startYesterday.setDate(startYesterday.getDate() - 1);
  if (date >= startToday) return t("today");
  if (date >= startYesterday) return t("yesterday");
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export function History() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);

  const { data: threads = [], isLoading } = useQuery({
    queryKey: ["threads"],
    queryFn: () => fetchThreads(token!),
    enabled: !!token,
  });

  const groups = new Map<string, typeof threads>();
  for (const th of threads) {
    const label = dayLabel(new Date(th.last_message_at));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label)!.push(th);
  }

  return (
    <div className="page">
      <h1>{t("history")}</h1>
      {isLoading && <p style={{ color: "var(--muted)" }}>{t("loading")}</p>}
      {[...groups.entries()].map(([label, items]) => (
        <div key={label}>
          <div className="section-title">{label}</div>
          {items.map((th) => (
            <button
              key={th.id}
              type="button"
              className="history-card"
              onClick={() => navigate(`/thread/${th.id}`)}
            >
              <div>{th.title}</div>
              <small style={{ color: "var(--muted)" }}>
                {th.message_count} вопросов •{" "}
                {new Date(th.last_message_at).toLocaleTimeString("ru-RU", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </small>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
