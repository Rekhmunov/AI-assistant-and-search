import { useState } from "react";
import { apiFetch } from "../api";

export interface ThreadSummary {
  id: string;
  title: string;
  message_count: number;
  last_message_at: string;
}

interface AdminMessage {
  id: string;
  role: string;
  content: string;
  content_truncated: boolean;
  created_at: string;
}

interface ThreadMessages {
  id: string;
  title: string;
  messages: AdminMessage[];
}

type Props = {
  userId: string;
  thread: ThreadSummary;
};

function previewLine(messages: AdminMessage[]): string | null {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser?.content) return null;
  const line = firstUser.content.replace(/\s+/g, " ").trim();
  return line.length > 120 ? `${line.slice(0, 120)}…` : line;
}

export function UserThreadPanel({ userId, thread }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<ThreadMessages | null>(null);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (data) return;
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<ThreadMessages>(
        `/api/admin/users/${userId}/threads/${thread.id}/messages`,
      );
      setData(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const preview = data ? previewLine(data.messages) : null;

  return (
    <div className={`thread-panel ${open ? "thread-panel-open" : ""}`}>
      <button type="button" className="thread-panel-head" onClick={toggle} aria-expanded={open}>
        <span className="thread-panel-chevron">{open ? "▼" : "▶"}</span>
        <span className="thread-panel-main">
          <span className="thread-panel-title">{thread.title}</span>
          <span className="thread-panel-meta">
            {thread.message_count} сообщ. ·{" "}
            {new Date(thread.last_message_at).toLocaleString("ru-RU")}
          </span>
          {!open && preview && <span className="thread-panel-preview">{preview}</span>}
        </span>
      </button>

      {open && (
        <div className="thread-panel-body">
          {loading && <p className="hint">Загрузка…</p>}
          {error && <p className="error">{error}</p>}
          {data && data.messages.length === 0 && <p className="hint">Сообщений нет</p>}
          {data?.messages.map((m) => (
            <div key={m.id} className={`thread-msg thread-msg-${m.role}`}>
              <div className="thread-msg-label">
                {m.role === "user" ? "Вопрос" : "Ответ"}
                <time dateTime={m.created_at}>
                  {new Date(m.created_at).toLocaleString("ru-RU", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
              </div>
              <pre className="thread-msg-text">{m.content}</pre>
              {m.content_truncated && (
                <p className="hint">Текст обрезан (слишком длинный для админки)</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
