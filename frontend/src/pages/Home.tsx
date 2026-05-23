import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchThreads } from "../api/client";
import { SearchBar } from "../components/SearchBar";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

const TOPICS = ["Технологии", "Бизнес", "Наука", "Мир"];

export function Home() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const [query, setQuery] = useState("");

  const { data: threads = [] } = useQuery({
    queryKey: ["threads"],
    queryFn: () => fetchThreads(token!),
    enabled: !!token,
  });

  const startSearch = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    navigate(`/thread?q=${encodeURIComponent(trimmed)}`);
  };

  return (
    <div className="page">
      <div className="logo">🔍 {t("appName")}</div>
      <SearchBar value={query} onChange={setQuery} onSubmit={() => startSearch(query)} />

      <div className="section-title">{t("popularTopics")}</div>
      <div className="chips">
        {TOPICS.map((topic) => (
          <button key={topic} type="button" className="chip" onClick={() => startSearch(topic)}>
            {topic}
          </button>
        ))}
      </div>

      <div className="section-title">{t("recentThreads")}</div>
      <div className="thread-list">
        {threads.slice(0, 5).map((th) => (
          <button key={th.id} type="button" onClick={() => navigate(`/thread/${th.id}`)}>
            <div>{th.title}</div>
            <small style={{ color: "var(--muted)" }}>
              {th.message_count} вопросов • {new Date(th.last_message_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
            </small>
          </button>
        ))}
      </div>
    </div>
  );
}
