import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch, apiUpload } from "../api";
import { useAuth } from "../AuthContext";
import { RichTextEditor } from "../components/RichTextEditor";
import { isWelcomeHtmlEmpty, welcomeTextToEditorHtml } from "../lib/welcomeText";

interface UserSearchResult {
  id: string;
  email: string;
  name: string;
  plan: string;
  max_user_id: number | null;
  has_max: boolean;
}

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

  // Direct message state
  const [dmSearchQ, setDmSearchQ] = useState("");
  const [dmSearchResults, setDmSearchResults] = useState<UserSearchResult[]>([]);
  const [dmSearchBusy, setDmSearchBusy] = useState(false);
  const [dmSelectedUser, setDmSelectedUser] = useState<UserSearchResult | null>(null);
  const [dmText, setDmText] = useState("");
  const [dmMediaType, setDmMediaType] = useState<WelcomeMediaType>("none");
  const [dmMediaToken, setDmMediaToken] = useState<string | null>(null);
  const [dmMediaFilename, setDmMediaFilename] = useState<string | null>(null);
  const [dmUploadBusy, setDmUploadBusy] = useState(false);
  const [dmSending, setDmSending] = useState(false);
  const [dmMsg, setDmMsg] = useState("");
  const [dmError, setDmError] = useState("");
  const dmFileInputRef = useRef<HTMLInputElement>(null);
  const dmSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
        setWelcomeText(welcomeTextToEditorHtml(data.text));
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
      setWelcomeText(welcomeTextToEditorHtml(updated.text));
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

  // Direct message handlers
  const onDmSearch = (q: string) => {
    setDmSearchQ(q);
    setDmSelectedUser(null);
    if (dmSearchTimer.current) clearTimeout(dmSearchTimer.current);
    if (!q.trim()) { setDmSearchResults([]); return; }
    dmSearchTimer.current = setTimeout(async () => {
      setDmSearchBusy(true);
      try {
        const res = await apiFetch<UserSearchResult[]>(`/api/admin/broadcasts/user-search?q=${encodeURIComponent(q.trim())}`);
        setDmSearchResults(res);
      } catch { setDmSearchResults([]); }
      finally { setDmSearchBusy(false); }
    }, 400);
  };

  const onDmMediaFile = async (file: File | null) => {
    if (!file) return;
    setDmUploadBusy(true);
    setDmError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiUpload<{ media_type: WelcomeMediaType; media_token: string; media_filename: string }>(
        "/api/admin/broadcasts/media", form
      );
      setDmMediaType(uploaded.media_type);
      setDmMediaToken(uploaded.media_token);
      setDmMediaFilename(uploaded.media_filename);
    } catch (e) { setDmError(String(e)); }
    finally { setDmUploadBusy(false); if (dmFileInputRef.current) dmFileInputRef.current.value = ""; }
  };

  const sendDirect = async () => {
    if (!dmSelectedUser || !canWrite) return;
    setDmSending(true);
    setDmMsg("");
    setDmError("");
    try {
      const res = await apiFetch<{ ok: boolean; error?: string; max_user_id?: number }>(
        "/api/admin/broadcasts/direct",
        {
          method: "POST",
          body: JSON.stringify({
            user_id: dmSelectedUser.id,
            text: dmText,
            media_type: dmMediaType,
            media_token: dmMediaToken,
            media_filename: dmMediaFilename,
          }),
        }
      );
      if (res.ok) {
        setDmMsg(`✅ Сообщение отправлено пользователю ${dmSelectedUser.email || dmSelectedUser.name} (MAX ID: ${res.max_user_id})`);
        setDmText("");
        setDmMediaType("none");
        setDmMediaToken(null);
        setDmMediaFilename(null);
      } else {
        setDmError(res.error || "Ошибка отправки");
      }
    } catch (e) { setDmError(String(e)); }
    finally { setDmSending(false); }
  };

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
        </div>
      </header>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}

      <section className="card broadcasts-section">
        <h2 className="broadcasts-section-title">Первое сообщение (/start)</h2>

        <form className="broadcasts-welcome-form" onSubmit={saveWelcome}>
          <div className="broadcasts-field broadcasts-field--wide">
            <span className="broadcasts-field-label">Текст сообщения</span>
            <RichTextEditor
              value={welcomeText}
              onChange={setWelcomeText}
              disabled={!canWrite || welcomeBusy}
            />
            <span className="hint broadcasts-char-count">
              Осталось символов: {welcomeCharsLeft}
              {welcomeCharsLeft < 0 && " — сократите текст"}
            </span>
          </div>

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
            <button
              type="submit"
              className="btn-primary"
              disabled={welcomeBusy || isWelcomeHtmlEmpty(welcomeText) || welcomeCharsLeft < 0}
            >
              {welcomeBusy ? "Сохранение…" : "Сохранить приветствие"}
            </button>
          )}
        </form>
      </section>

      {/* ── Direct message ──────────────────────────────────────────────── */}
      {canWrite && (
        <section className="card broadcasts-section">
          <h2 className="broadcasts-section-title">Личное сообщение</h2>
          <p className="hint" style={{ marginBottom: 12 }}>
            Найдите пользователя по e-mail или MAX ID и отправьте ему сообщение напрямую через бота.
          </p>

          {/* Search */}
          <div className="broadcasts-field" style={{ marginBottom: 8 }}>
            <span className="broadcasts-field-label">Поиск пользователя</span>
            <input
              type="text"
              className="broadcasts-dm-search"
              placeholder="E-mail, имя или MAX ID..."
              value={dmSearchQ}
              onChange={(e) => onDmSearch(e.target.value)}
              style={{ width: "100%", padding: "8px 10px", borderRadius: 8, border: "1px solid #d1d5db", fontSize: 14, boxSizing: "border-box" }}
            />
          </div>

          {dmSearchBusy && <p className="hint">Поиск…</p>}

          {!dmSelectedUser && dmSearchResults.length > 0 && (
            <ul className="broadcasts-dm-results">
              {dmSearchResults.map((u) => (
                <li key={u.id} className="broadcasts-dm-result" onClick={() => { setDmSelectedUser(u); setDmSearchQ(u.email || u.name); setDmSearchResults([]); }}>
                  <span className="broadcasts-dm-result-name">{u.email || u.name || "—"}</span>
                  {u.name && u.email && <span className="broadcasts-dm-result-sub">{u.name}</span>}
                  <span className={"broadcasts-dm-result-plan broadcasts-dm-result-plan--" + u.plan}>{u.plan.toUpperCase()}</span>
                  {u.has_max
                    ? <span className="broadcasts-dm-result-max">MAX {u.max_user_id}</span>
                    : <span className="broadcasts-dm-result-nomax">Нет MAX ID</span>}
                </li>
              ))}
            </ul>
          )}

          {!dmSelectedUser && dmSearchQ.trim() && !dmSearchBusy && dmSearchResults.length === 0 && (
            <p className="hint" style={{ marginBottom: 8 }}>Пользователи не найдены</p>
          )}

          {dmSelectedUser && (
            <div className="broadcasts-dm-selected">
              <span>
                <strong>{dmSelectedUser.email || dmSelectedUser.name}</strong>
                {dmSelectedUser.name && dmSelectedUser.email && <> — {dmSelectedUser.name}</>}
                &nbsp;·&nbsp;{dmSelectedUser.plan.toUpperCase()}
                {dmSelectedUser.has_max
                  ? <> &nbsp;·&nbsp; MAX {dmSelectedUser.max_user_id}</>
                  : <> &nbsp;·&nbsp; <span style={{ color: "#dc2626" }}>Нет MAX ID</span></>}
              </span>
              <button
                type="button"
                className="btn-secondary"
                style={{ marginLeft: 12, fontSize: 12, padding: "2px 10px" }}
                onClick={() => { setDmSelectedUser(null); setDmSearchQ(""); setDmSearchResults([]); }}
              >
                Изменить
              </button>
            </div>
          )}

          {dmSelectedUser && !dmSelectedUser.has_max && (
            <p className="error" style={{ marginTop: 8 }}>Пользователь не запускал бота — MAX ID отсутствует. Сообщение не будет доставлено.</p>
          )}

          {dmSelectedUser && dmSelectedUser.has_max && (
            <>
              <div className="broadcasts-field broadcasts-field--wide" style={{ marginTop: 12 }}>
                <span className="broadcasts-field-label">Текст сообщения</span>
                <textarea
                  rows={4}
                  value={dmText}
                  onChange={(e) => setDmText(e.target.value)}
                  placeholder="Текст личного сообщения в MAX"
                  maxLength={4000}
                  style={{ width: "100%", boxSizing: "border-box" }}
                />
              </div>

              <div className="broadcasts-welcome-media" style={{ marginTop: 8 }}>
                <span className="broadcasts-field-label">Медиа (необязательно)</span>
                <div className="broadcasts-media-toolbar">
                  <label className="btn-secondary broadcasts-file-btn">
                    {dmUploadBusy ? "Загрузка…" : "Загрузить фото или видео"}
                    <input
                      ref={dmFileInputRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/webm,video/quicktime"
                      hidden
                      disabled={dmUploadBusy}
                      onChange={(e) => void onDmMediaFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                  {dmMediaFilename && (
                    <span className="broadcasts-media-name">
                      {dmMediaType === "video" ? "🎬" : "🖼"} {dmMediaFilename}
                    </span>
                  )}
                  {dmMediaToken && (
                    <button
                      type="button"
                      className="btn-secondary btn-danger-outline"
                      disabled={dmUploadBusy}
                      onClick={() => { setDmMediaType("none"); setDmMediaToken(null); setDmMediaFilename(null); }}
                    >
                      Убрать
                    </button>
                  )}
                </div>
              </div>

              {dmError && <p className="error" style={{ marginTop: 8 }}>{dmError}</p>}
              {dmMsg && <p className="ok" style={{ marginTop: 8 }}>{dmMsg}</p>}

              <button
                type="button"
                className="btn-primary"
                style={{ marginTop: 12 }}
                disabled={dmSending || (!dmText.trim() && !dmMediaToken)}
                onClick={() => void sendDirect()}
              >
                {dmSending ? "Отправка…" : "Отправить сообщение"}
              </button>
            </>
          )}
        </section>
      )}

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
