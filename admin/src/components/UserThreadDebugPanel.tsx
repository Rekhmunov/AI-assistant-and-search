import { useState } from "react";
import { apiFetch } from "../api";

export interface ThreadSummary {
  id: string;
  title: string;
  message_count: number;
  last_message_at: string;
  deleted_at: string | null;
  deleted_by_user: boolean;
}

interface AdminMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
  sources: Array<Record<string, unknown>> | null;
  follow_up_questions: string[] | null;
  debug_trace: Record<string, unknown> | null;
}

interface SearchTurn {
  user_message: AdminMessage;
  assistant_message: AdminMessage | null;
}

interface ThreadDebug {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string;
  deleted_at: string | null;
  deleted_by_user: boolean;
  turns: SearchTurn[];
}

type Props = {
  userId: string;
  thread: ThreadSummary;
};

export function UserThreadDebugPanel({ userId, thread }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<ThreadDebug | null>(null);

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
      const res = await apiFetch<ThreadDebug>(
        `/api/admin/users/${userId}/threads/${thread.id}/debug`,
      );
      setData(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`thread-panel debug-panel ${open ? "thread-panel-open" : ""}`}>
      <button type="button" className="thread-panel-head" onClick={toggle} aria-expanded={open}>
        <span className="thread-panel-chevron">{open ? "▼" : "▶"}</span>
        <span className="thread-panel-main">
          <span className="thread-panel-title">
            {thread.title}
            {thread.deleted_by_user && <span className="badge bad">удалён пользователем</span>}
          </span>
          <span className="thread-panel-meta">
            {thread.message_count} сообщ. ·{" "}
            {new Date(thread.last_message_at).toLocaleString("ru-RU")}
          </span>
          <span className="thread-panel-cta">▶ Нажмите — расшифровка Yandex (Search + GPT)</span>
        </span>
      </button>

      {open && (
        <div className="thread-panel-body debug-panel-body">
          {loading && <p className="hint">Загрузка отладки…</p>}
          {error && <p className="error">{error}</p>}
          {data && data.turns.length === 0 && <p className="hint">Нет сообщений</p>}
          {data?.turns.map((turn, idx) => (
            <div key={turn.user_message.id} className="debug-turn">
              <h4>Запрос {idx + 1}</h4>
              <DebugBlock title="Вопрос пользователя (в UI)" content={turn.user_message.content} />
              {turn.assistant_message ? (
                <>
                  <DebugBlock
                    title="Ответ ассистента"
                    content={turn.assistant_message.content}
                  />
                  <DebugTrace trace={turn.assistant_message.debug_trace} />
                  {turn.assistant_message.follow_up_questions &&
                    turn.assistant_message.follow_up_questions.length > 0 && (
                      <div className="debug-meta">
                        <strong>Follow-ups:</strong>{" "}
                        {turn.assistant_message.follow_up_questions.join(" · ")}
                      </div>
                    )}
                </>
              ) : (
                <p className="hint">Ответ не получен</p>
              )}
            </div>
          ))}
          {data &&
            data.turns.length > 0 &&
            !data.turns.some((t) => t.assistant_message?.debug_trace) && (
              <p className="error">
                debug_trace пуст. Проверьте: backend обновлён и выполнена миграция{" "}
                <code>alembic upgrade head</code>, затем сделайте новый поиск.
              </p>
            )}
        </div>
      )}
    </div>
  );
}

function DebugBlock({ title, content }: { title: string; content: string }) {
  return (
    <div className="debug-block">
      <div className="debug-block-title">{title}</div>
      <pre className="debug-pre">{content}</pre>
    </div>
  );
}

function DebugTrace({ trace }: { trace: Record<string, unknown> | null }) {
  if (!trace) {
    return (
      <div className="debug-trace debug-trace-empty">
        <div className="debug-block-title">Пайплайн Yandex</div>
        <p className="hint">
          Нет сохранённой расшифровки (запрос до деплоя или миграция 006 не применена). Сделайте новый
          поиск после обновления backend.
        </p>
      </div>
    );
  }

  const route = trace.route as Record<string, unknown> | undefined;
  const search = trace.yandex_search as Record<string, unknown> | null | undefined;
  const gpt = trace.yandex_gpt as Record<string, unknown> | undefined;

  return (
    <div className="debug-trace">
      <div className="debug-block-title">Пайплайн Yandex</div>

      {trace.llm_query != null && (
        <DebugBlock title="Запрос в LLM (нормализованный)" content={String(trace.llm_query)} />
      )}

      {route && (
        <div className="debug-meta">
          <strong>Роутер:</strong> search={String(route.needs_search)} · модель={String(route.answer_model)}{" "}
          · причина={String(route.reason)}
          <br />
          <strong>search_query (роутер):</strong> {String(route.search_query)}
        </div>
      )}

      {search && (
        <>
          <div className="debug-meta">
            <strong>Yandex Search:</strong> запрос «{String(search.query_sent)}» · источников:{" "}
            {String(search.sources_count)}
          </div>
          <details className="debug-details">
            <summary>Источники из Search API</summary>
            <pre className="debug-pre small">
              {JSON.stringify(search.sources, null, 2)}
            </pre>
          </details>
        </>
      )}

      {search === null && route && !route.needs_search && (
        <div className="debug-meta">Yandex Search не вызывался (ответ по контексту диалога)</div>
      )}

      {gpt && (
        <div className="debug-meta">
          <strong>Yandex GPT:</strong> mode={String(gpt.mode)} · model={String(gpt.model)}
          <br />
          <strong>model_uri:</strong> {String(gpt.model_uri)}
        </div>
      )}

      {gpt?.messages_to_api != null && (
        <details className="debug-details">
          <summary>Промпт в YandexGPT (system + user)</summary>
          <pre className="debug-pre small">
            {JSON.stringify(gpt.messages_to_api, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
