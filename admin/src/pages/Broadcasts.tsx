import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiUpload } from "../api";
import { useAuth } from "../AuthContext";

type Audience = "all" | "free" | "pro";
type WelcomeMediaType = "none" | "image" | "video";

interface Broadcast {
  id: string;
  text: string;
  media_type: WelcomeMediaType;
  media_token: string | null;
  media_filename: string | null;
  audience: Audience;
  status: string;
  sent_count: number;
  failed_count: number;
  created_at: string;
}

interface BotWelcome {
  text: string;
  media_type: WelcomeMediaType;
  media_token: string | null;
  media_filename: string | null;
  webhook_url: string;
  max_text_length: number;
}

const AUDIENCE_LABEL: Record<Audience, string> = {
  all: "Все",
  free: "Free",
  pro: "Pro",
};

const STATUS_LABEL: Record<string, string> = {
  draft: "черновик",
  sending: "отправка",
  done: "отправлено",
  failed: "ошибка",
};

export function BroadcastsPage() {
  const { can } = useAuth();
  const canWrite = can("broadcasts:write");

  const [items, setItems] = useState<Broadcast[]>([]);
  const [text, setText] = useState("");
  const [broadcastMediaType, setBroadcastMediaType] = useState<WelcomeMediaType>("none");
  const [broadcastMediaToken, setBroadcastMediaToken] = useState<string | null>(null);
  const [broadcastMediaFilename, setBroadcastMediaFilename] = useState<string | null>(null);
  const [broadcastUploadBusy, setBroadcastUploadBusy] = useState(false);
  const broadcastFileInputRef = useRef<HTMLInputElement>(null);
  const [audience, setAudience] = useState<Audience>("all");
  const [preview, setPreview] = useState<number | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [clearHistoryConfirm, setClearHistoryConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [draftPreview, setDraftPreview] = useState<number | null>(null);

  const [welcome, setWelcome] = useState<BotWelcome | null>(null);
  const [welcomeText, setWelcomeText] = useState("");
  const [welcomeMediaType, setWelcomeMediaType] = useState<WelcomeMediaType>("none");
  const [welcomeMediaToken, setWelcomeMediaToken] = useState<string | null>(null);
  const [welcomeMediaFilename, setWelcomeMediaFilename] = useState<string | null>(null);
  const [welcomeBusy, setWelcomeBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    apiFetch<Broadcast[]>("/api/admin/broadcasts")
      .then(setItems)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const loadWelcome = useCallback(() => {
    apiFetch<BotWelcome>("/api/admin/broadcasts/welcome")
      .then((data) => {
        setWelcome(data);
        setWelcomeText(data.text);
        setWelcomeMediaType(data.media_type);
        setWelcomeMediaToken(data.media_token);
        setWelcomeMediaFilename(data.media_filename);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    load();
    loadWelcome();
  }, [load, loadWelcome]);

  useEffect(() => {
    setPreviewError("");
    apiFetch<{ recipient_count: number }>(`/api/admin/broadcasts/audience-preview?audience=${audience}`)
      .then((r) => setPreview(r.recipient_count))
      .catch((e) => {
        setPreview(null);
        setPreviewError(String(e));
      });
  }, [audience]);

  const onBroadcastFile = async (file: File | null) => {
    if (!file || !canWrite) return;
    setBroadcastUploadBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiUpload<{
        media_type: WelcomeMediaType;
        media_token: string;
        media_filename: string;
      }>("/api/admin/broadcasts/media", form);
      setBroadcastMediaType(uploaded.media_type);
      setBroadcastMediaToken(uploaded.media_token);
      setBroadcastMediaFilename(uploaded.media_filename);
      setMsg("Медиа для рассылки загружено в MAX");
    } catch (e) {
      setError(String(e));
    } finally {
      setBroadcastUploadBusy(false);
      if (broadcastFileInputRef.current) broadcastFileInputRef.current.value = "";
    }
  };

  const clearBroadcastMedia = () => {
    setBroadcastMediaType("none");
    setBroadcastMediaToken(null);
    setBroadcastMediaFilename(null);
  };

  const canCreateDraft =
    text.trim().length > 0 || (broadcastMediaType !== "none" && Boolean(broadcastMediaToken));

  const create = async () => {
    setError("");
    setMsg("");
    try {
      await apiFetch("/api/admin/broadcasts", {
        method: "POST",
        body: JSON.stringify({
          text,
          audience,
          media_type: broadcastMediaType,
          media_token: broadcastMediaToken,
          media_filename: broadcastMediaFilename,
        }),
      });
      setText("");
      clearBroadcastMedia();
      setMsg("Черновик рассылки создан");
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const removeOne = async (id: string) => {
    setError("");
    setMsg("");
    setDeleting(true);
    try {
      await apiFetch(`/api/admin/broadcasts/${id}`, { method: "DELETE" });
      setDeleteConfirmId(null);
      setConfirmId((prev) => (prev === id ? null : prev));
      setMsg("Рассылка удалена");
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setDeleting(false);
    }
  };

  const clearHistory = async () => {
    setError("");
    setMsg("");
    setDeleting(true);
    try {
      const res = await apiFetch<{ deleted: number }>("/api/admin/broadcasts", { method: "DELETE" });
      setClearHistoryConfirm(false);
      setConfirmId(null);
      setDeleteConfirmId(null);
      setMsg(`Удалено рассылок: ${res.deleted}`);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setDeleting(false);
    }
  };

  const send = async (id: string, draftAudience: Audience) => {
    setError("");
    setMsg("");
    try {
      const countRes = await apiFetch<{ recipient_count: number }>(
        `/api/admin/broadcasts/audience-preview?audience=${draftAudience}`,
      );
      await apiFetch(`/api/admin/broadcasts/${id}/send`, { method: "POST" });
      setConfirmId(null);
      setMsg(`Рассылка запущена (~${countRes.recipient_count} получателей в MAX)`);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const saveWelcome = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setWelcomeBusy(true);
    setError("");
    setMsg("");
    try {
      const updated = await apiFetch<BotWelcome>("/api/admin/broadcasts/welcome", {
        method: "PUT",
        body: JSON.stringify({
          text: welcomeText,
          media_type: welcomeMediaType,
          media_token: welcomeMediaToken,
          media_filename: welcomeMediaFilename,
        }),
      });
      setWelcome(updated);
      setMsg("Приветственное сообщение сохранено");
    } catch (e) {
      setError(String(e));
    } finally {
      setWelcomeBusy(false);
    }
  };

  const onWelcomeFile = async (file: File | null) => {
    if (!file || !canWrite) return;
    setUploadBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiUpload<{
        media_type: WelcomeMediaType;
        media_token: string;
        media_filename: string;
      }>("/api/admin/broadcasts/welcome/media", form);
      setWelcomeMediaType(uploaded.media_type);
      setWelcomeMediaToken(uploaded.media_token);
      setWelcomeMediaFilename(uploaded.media_filename);
      setMsg("Медиафайл загружен в MAX");
    } catch (e) {
      setError(String(e));
    } finally {
      setUploadBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const clearWelcomeMedia = async () => {
    if (!canWrite) return;
    setUploadBusy(true);
    setError("");
    try {
      await apiFetch("/api/admin/broadcasts/welcome/media", { method: "DELETE" });
      setWelcomeMediaType("none");
      setWelcomeMediaToken(null);
      setWelcomeMediaFilename(null);
      setMsg("Медиа удалено");
    } catch (e) {
      setError(String(e));
    } finally {
      setUploadBusy(false);
    }
  };

  const welcomeCharsLeft = useMemo(() => {
    const max = welcome?.max_text_length ?? 4000;
    return max - welcomeText.length;
  }, [welcome?.max_text_length, welcomeText.length]);

  const openSendConfirm = async (draft: Broadcast) => {
    setDraftPreview(null);
    setConfirmId(draft.id);
    try {
      const r = await apiFetch<{ recipient_count: number }>(
        `/api/admin/broadcasts/audience-preview?audience=${draft.audience}`,
      );
      setDraftPreview(r.recipient_count);
    } catch {
      setDraftPreview(null);
    }
  };

  return (
    <div className="admin-page admin-page--broadcasts">
      <header className="admin-page-header">
        <div>
          <h1>Рассылки</h1>
          <p className="admin-page-subtitle">
            Приветствие при /start в боте MAX и массовые сообщения подписчикам с привязанным MAX.
          </p>
        </div>
      </header>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}

      <section className="card broadcasts-section">
        <h2 className="broadcasts-section-title">Первое сообщение (/start)</h2>
        <p className="hint broadcasts-section-hint">
          Отправляется один раз, когда пользователь нажимает «Старт» в боте. Поддерживаются текст, изображение или
          видео.
        </p>

        {welcome && (
          <p className="hint broadcasts-webhook-hint">
            Webhook MAX: <code>{welcome.webhook_url}</code>
          </p>
        )}

        <form className="broadcasts-welcome-form" onSubmit={saveWelcome}>
          <label className="broadcasts-field broadcasts-field--wide">
            <span className="broadcasts-field-label">Текст сообщения</span>
            <textarea
              rows={6}
              value={welcomeText}
              onChange={(e) => setWelcomeText(e.target.value)}
              disabled={!canWrite || welcomeBusy}
              maxLength={welcome?.max_text_length ?? 4000}
              placeholder="Привет! Это Glosix — умный поиск с ответами и источниками."
            />
            <span className="hint broadcasts-char-count">Осталось символов: {welcomeCharsLeft}</span>
          </label>

          <div className="broadcasts-welcome-media">
            <span className="broadcasts-field-label">Медиа</span>
            <div className="broadcasts-media-toolbar">
              <label className="btn-secondary broadcasts-file-btn">
                {uploadBusy ? "Загрузка…" : "Загрузить фото или видео"}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime"
                  hidden
                  disabled={!canWrite || uploadBusy}
                  onChange={(e) => void onWelcomeFile(e.target.files?.[0] ?? null)}
                />
              </label>
              {welcomeMediaFilename && (
                <span className="broadcasts-media-name">
                  {welcomeMediaType === "video" ? "🎬" : "🖼"} {welcomeMediaFilename}
                </span>
              )}
              {welcomeMediaToken && canWrite && (
                <button
                  type="button"
                  className="btn-secondary btn-danger-outline"
                  disabled={uploadBusy}
                  onClick={() => void clearWelcomeMedia()}
                >
                  Убрать медиа
                </button>
              )}
            </div>
            <p className="hint">jpg, png, webp, gif, mp4, mov, webm — до 50 МБ. Файл загружается в MAX.</p>
          </div>

          {canWrite && (
            <button type="submit" className="btn-primary" disabled={welcomeBusy || !welcomeText.trim()}>
              {welcomeBusy ? "Сохранение…" : "Сохранить приветствие"}
            </button>
          )}
        </form>
      </section>

      <section className="card broadcasts-section broadcasts-rules">
        <h2 className="broadcasts-section-title">Правила MAX — чтобы не получить бан</h2>
        <ul className="broadcasts-rules-list">
          <li>Рассылка только пользователям, которые сами нажали «Старт» в боте (есть MAX ID).</li>
          <li>Не чаще 5 запусков рассылки в час; между сообщениями — пауза (~8/сек).</li>
          <li>Лимит API MAX — около 30 запросов/сек; при 429 рассылка ждёт и повторяет.</li>
          <li>Текст до 4000 символов; можно добавить фото или видео над текстом (как в приветствии).</li>
          <li>Медиа загружается в MAX до отправки; при ошибке «attachment.not.ready» бот повторит отправку.</li>
          <li>Сервисные сообщения (Pro, статус) — ок; массовые акции — редко и по делу.</li>
          <li>
            Webhook: подписка через API MAX (<code>POST /subscriptions</code>), не в ЛК. Секрет — в{" "}
            <code>MAX_BOT_WEBHOOK_SECRET</code>; MAX пришлёт заголовок <code>X-Max-Bot-Api-Secret</code>.
          </li>
        </ul>
      </section>

      {canWrite && (
        <section className="card broadcasts-section">
          <h2 className="broadcasts-section-title">Новая рассылка</h2>
          <div className="broadcasts-compose">
            <label className="broadcasts-field">
              <span className="broadcasts-field-label">Аудитория</span>
              <select value={audience} onChange={(e) => setAudience(e.target.value as Audience)}>
                <option value="all">Все с MAX</option>
                <option value="free">Free</option>
                <option value="pro">Pro</option>
              </select>
            </label>
            <p className="hint broadcasts-recipients">
              Получателей в MAX: {previewError ? "—" : preview ?? "…"}
              {previewError && <span className="broadcasts-preview-error"> ({previewError})</span>}
            </p>
            <div className="broadcasts-welcome-media">
              <span className="broadcasts-field-label">Медиа над текстом</span>
              <div className="broadcasts-media-toolbar">
                <label className="btn-secondary broadcasts-file-btn">
                  {broadcastUploadBusy ? "Загрузка…" : "Загрузить фото или видео"}
                  <input
                    ref={broadcastFileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime"
                    hidden
                    disabled={broadcastUploadBusy}
                    onChange={(e) => void onBroadcastFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                {broadcastMediaFilename && (
                  <span className="broadcasts-media-name">
                    {broadcastMediaType === "video" ? "🎬" : "🖼"} {broadcastMediaFilename}
                  </span>
                )}
                {broadcastMediaToken && (
                  <button
                    type="button"
                    className="btn-secondary btn-danger-outline"
                    disabled={broadcastUploadBusy}
                    onClick={clearBroadcastMedia}
                  >
                    Убрать медиа
                  </button>
                )}
              </div>
              <p className="hint">Фото или видео появится в MAX над текстом сообщения.</p>
            </div>
            <label className="broadcasts-field broadcasts-field--wide">
              <span className="broadcasts-field-label">Текст рассылки</span>
              <textarea
                rows={5}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Текст сообщения в MAX (под медиа)"
                maxLength={4096}
              />
            </label>
            <button
              type="button"
              className="btn-primary"
              disabled={!canCreateDraft}
              onClick={() => void create()}
            >
              Создать черновик
            </button>
          </div>
        </section>
      )}

      <section className="broadcasts-history">
        <header className="broadcasts-history-header">
          <div className="broadcasts-history-header-left">
            <h2 className="broadcasts-section-title">История</h2>
            {!loading && <span className="admin-count-badge">{items.length}</span>}
          </div>
          {canWrite && !loading && items.length > 0 && (
            <div className="broadcasts-history-header-actions">
              {clearHistoryConfirm ? (
                <>
                  <span className="hint">Удалить всю историю рассылок?</span>
                  <button
                    type="button"
                    className="btn-secondary btn-danger-outline"
                    disabled={deleting}
                    onClick={() => void clearHistory()}
                  >
                    {deleting ? "Удаление…" : "Да, очистить"}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={deleting}
                    onClick={() => setClearHistoryConfirm(false)}
                  >
                    Отмена
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="btn-secondary btn-danger-outline"
                  onClick={() => setClearHistoryConfirm(true)}
                >
                  Очистить всю историю
                </button>
              )}
            </div>
          )}
        </header>

        {loading && <p className="hint">Загрузка…</p>}

        {!loading && items.length === 0 && <p className="hint card broadcasts-empty">Рассылок пока нет</p>}

        {items.map((b) => (
          <div key={b.id} className="card broadcasts-history-item">
            <p className="broadcasts-history-text">{b.text}</p>
            {b.media_type !== "none" && b.media_filename && (
              <p className="hint broadcasts-history-media">
                {b.media_type === "video" ? "Видео" : "Фото"}: {b.media_filename}
              </p>
            )}
            <p className="hint broadcasts-history-meta">
              {AUDIENCE_LABEL[b.audience] ?? b.audience} · {STATUS_LABEL[b.status] ?? b.status} · отправлено{" "}
              {b.sent_count} · ошибок {b.failed_count} · {new Date(b.created_at).toLocaleString("ru-RU")}
            </p>
            {canWrite && (
              <div className="broadcasts-history-actions">
                {b.status === "draft" && (
                  <>
                    {confirmId === b.id ? (
                      <>
                        <span className="hint">
                          Отправить аудитории «{AUDIENCE_LABEL[b.audience]}» (~{draftPreview ?? "…"} в MAX)?
                        </span>
                        <button type="button" className="btn-primary" onClick={() => void send(b.id, b.audience)}>
                          Да, отправить
                        </button>
                        <button type="button" className="btn-secondary" onClick={() => setConfirmId(null)}>
                          Отмена
                        </button>
                      </>
                    ) : (
                      <button type="button" className="btn-primary" onClick={() => void openSendConfirm(b)}>
                        Отправить
                      </button>
                    )}
                  </>
                )}
                {b.status !== "sending" &&
                  (deleteConfirmId === b.id ? (
                    <>
                      <span className="hint">Удалить эту рассылку из истории?</span>
                      <button
                        type="button"
                        className="btn-secondary btn-danger-outline"
                        disabled={deleting}
                        onClick={() => void removeOne(b.id)}
                      >
                        {deleting ? "Удаление…" : "Да, удалить"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={deleting}
                        onClick={() => setDeleteConfirmId(null)}
                      >
                        Отмена
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary btn-danger-outline"
                      disabled={deleting}
                      onClick={() => {
                        setDeleteConfirmId(b.id);
                        setClearHistoryConfirm(false);
                      }}
                    >
                      Удалить
                    </button>
                  ))}
                {b.status === "sending" && (
                  <span className="hint">Удаление недоступно во время отправки</span>
                )}
              </div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}
