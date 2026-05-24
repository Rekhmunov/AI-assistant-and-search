import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type Audience = "all" | "free" | "pro";

interface Broadcast {
  id: string;
  text: string;
  audience: Audience;
  status: string;
  sent_count: number;
  failed_count: number;
  created_at: string;
}

export function BroadcastsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Broadcast[]>([]);
  const [text, setText] = useState("");
  const [audience, setAudience] = useState<Audience>("all");
  const [preview, setPreview] = useState(0);
  const [error, setError] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Broadcast[]>("/api/admin/broadcasts")
      .then(setItems)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    apiFetch<{ recipient_count: number }>(`/api/admin/broadcasts/audience-preview?audience=${audience}`)
      .then((r) => setPreview(r.recipient_count))
      .catch(() => setPreview(0));
  }, [audience]);

  const create = async () => {
    setError("");
    try {
      await apiFetch("/api/admin/broadcasts", {
        method: "POST",
        body: JSON.stringify({ text, audience }),
      });
      setText("");
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const send = async (id: string) => {
    setError("");
    try {
      await apiFetch(`/api/admin/broadcasts/${id}/send`, { method: "POST" });
      setConfirmId(null);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div>
      <h1>Рассылки</h1>
      {error && <p className="error">{error}</p>}
      {can("broadcasts:write") && (
        <div className="card">
          <h2>Новая рассылка</h2>
          <label>
            Аудитория
            <select value={audience} onChange={(e) => setAudience(e.target.value as Audience)}>
              <option value="all">Все</option>
              <option value="free">Free</option>
              <option value="pro">Pro</option>
            </select>
          </label>
          <p className="hint">Получателей: ~{preview}</p>
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Текст сообщения в MAX" />
          <button type="button" className="btn-primary" disabled={!text.trim()} onClick={create}>
            Создать черновик
          </button>
        </div>
      )}
      <h2>История</h2>
      {items.map((b) => (
        <div key={b.id} className="card">
          <p>{b.text}</p>
          <small>
            {b.audience} · {b.status} · sent {b.sent_count} · failed {b.failed_count}
          </small>
          {b.status === "draft" && can("broadcasts:write") && (
            <div className="row-actions">
              {confirmId === b.id ? (
                <>
                  <span>Отправить ~{preview} пользователям?</span>
                  <button type="button" className="btn-primary" onClick={() => send(b.id)}>
                    Да, отправить
                  </button>
                  <button type="button" className="btn-secondary" onClick={() => setConfirmId(null)}>
                    Отмена
                  </button>
                </>
              ) : (
                <button type="button" className="btn-primary" onClick={() => setConfirmId(b.id)}>
                  Отправить
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
