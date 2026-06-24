import { useState, useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "";

const TIMEZONES = [
  { value: "Europe/Moscow", label: "Москва (UTC+3)" },
  { value: "Europe/Kaliningrad", label: "Калининград (UTC+2)" },
  { value: "Europe/Samara", label: "Самара (UTC+4)" },
  { value: "Asia/Yekaterinburg", label: "Екатеринбург (UTC+5)" },
  { value: "Asia/Omsk", label: "Омск (UTC+6)" },
  { value: "Asia/Krasnoyarsk", label: "Красноярск (UTC+7)" },
  { value: "Asia/Irkutsk", label: "Иркутск (UTC+8)" },
  { value: "Asia/Vladivostok", label: "Владивосток (UTC+10)" },
  { value: "Asia/Kamchatka", label: "Камчатка (UTC+12)" },
  { value: "UTC", label: "UTC" },
  { value: "Asia/Almaty", label: "Алматы (UTC+5)" },
  { value: "Asia/Dubai", label: "Дубай (UTC+4)" },
];

type HistoryItem = { id: string; topic: string; status: string; at: string; text: string };

const DAY_OPTIONS = [
  { key: "mon", label: "Понедельник" },
  { key: "tue", label: "Вторник" },
  { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" },
  { key: "fri", label: "Пятница" },
  { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" },
];

const DAY_SHORT: Record<string, string> = {
  mon: "Пн", tue: "Вт", wed: "Ср", thu: "Чт", fri: "Пт", sat: "Сб", sun: "Вс",
};

type ScheduleSlot = { day: string; time: string };

type PosterConfig = {
  poster_channel_id: string;
  poster_topics: string;
  poster_tone: string;
  poster_emoji: boolean;
  poster_length: string;
  poster_cta: boolean;
  poster_media: string;
  poster_schedule: ScheduleSlot[];
  poster_timezone: string;
  poster_approval: boolean;
  poster_reflection: boolean;
};

const DEFAULTS: PosterConfig = {
  poster_channel_id: "",
  poster_topics: "",
  poster_tone: "official",
  poster_emoji: true,
  poster_length: "medium",
  poster_cta: false,
  poster_media: "none",
  poster_schedule: [],
  poster_timezone: "Europe/Moscow",
  poster_approval: true,
  poster_reflection: true,
};

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
};

export function PosterSettingsPanel({ threadId, initialConfig, enabled, onToggle }: Props) {
  const token = useAuthStore((s) => s.token);
  const [cfg, setCfg] = useState<PosterConfig>({ ...DEFAULTS });
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [draft, setDraft] = useState<{ postId: string; text: string; topic: string } | null>(null);
  const [draftAction, setDraftAction] = useState<"" | "actioning" | "editing" | "published" | "rejected" | "error">("");
  const [draftError, setDraftError] = useState("");
  const [editedText, setEditedText] = useState("");
  const [activationStatus, setActivationStatus] = useState<"idle" | "active" | "inactive" | "error">("idle");
  const [activationHint, setActivationHint] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const initDone = useRef(false);

  // If agent already configured (has channel), show active UI without requiring re-save
  const isConfigured = Boolean(
    (initialConfig?.poster_channel_id as string | undefined)?.trim()
  );
  const showActiveUI = activationStatus === "active" || (isConfigured && enabled && activationStatus === "idle");

  const loadHistory = useCallback(async () => {
    if (!showActiveUI) return;
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/post-history`, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setHistory(data.items || []);
      }
    } catch { /* silent */ } finally {
      setHistoryLoading(false);
    }
  }, [threadId, token, activationStatus]);

  // Load history on mount if already configured
  useEffect(() => {
    if (isConfigured && enabled) {
      void loadHistory();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!initialConfig || initDone.current) return;
    initDone.current = true;

    // Support both legacy (poster_days + poster_time) and new poster_schedule
    let schedule: ScheduleSlot[] = [];
    if (Array.isArray(initialConfig.poster_schedule)) {
      schedule = initialConfig.poster_schedule as ScheduleSlot[];
    } else if (Array.isArray(initialConfig.poster_days) && (initialConfig.poster_days as string[]).length > 0) {
      const time = String(initialConfig.poster_time ?? "10:00");
      schedule = (initialConfig.poster_days as string[]).map((day) => ({ day, time }));
    }

    setCfg({
      poster_channel_id: String(initialConfig.poster_channel_id ?? ""),
      poster_topics: String(initialConfig.poster_topics ?? ""),
      poster_tone: String(initialConfig.poster_tone ?? "official"),
      poster_emoji: initialConfig.poster_emoji !== false,
      poster_length: String(initialConfig.poster_length ?? "medium"),
      poster_cta: Boolean(initialConfig.poster_cta),
      poster_media: String(initialConfig.poster_media ?? "none"),
      poster_schedule: schedule,
      poster_timezone: String(initialConfig.poster_timezone ?? "Europe/Moscow"),
      poster_approval: initialConfig.poster_approval !== false,
      poster_reflection: initialConfig.poster_reflection !== false,
    });
  }, [initialConfig]);

  const patch = <K extends keyof PosterConfig>(key: K, value: PosterConfig[K]) =>
    setCfg((c) => ({ ...c, [key]: value }));

  // Schedule slot operations
  const addSlot = () => {
    patch("poster_schedule", [...cfg.poster_schedule, { day: "mon", time: "10:00" }]);
  };

  const updateSlot = (idx: number, field: keyof ScheduleSlot, value: string) => {
    const slots = cfg.poster_schedule.map((s, i) => i === idx ? { ...s, [field]: value } : s);
    patch("poster_schedule", slots);
  };

  const removeSlot = (idx: number) => {
    patch("poster_schedule", cfg.poster_schedule.filter((_, i) => i !== idx));
  };

  const handleToggle = (val: boolean) => {
    onToggle(val);
    if (!val) {
      setActivationStatus("inactive");
      setError("");
    } else {
      setActivationStatus("idle");
    }
  };

  // Validation
  const channelOk = cfg.poster_channel_id.trim() !== "";
  const topicsOk = cfg.poster_topics.trim() !== "";
  const canSave = enabled && channelOk && topicsOk && !saving;

  const validationHint = !enabled ? ""
    : !channelOk && !topicsOk ? "Укажите канал и темы публикаций"
    : !channelOk ? "Укажите канал MAX"
    : !topicsOk ? "Укажите темы публикаций"
    : "";

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setError("");
    setActivationStatus("idle");
    try {
      // Step 1: Save config
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error("Не удалось сохранить настройки");
      setSaving(false);

      // Step 2: Verify channel admin status
      setVerifying(true);
      const verifyRes = await fetch(`${API_BASE}/api/agent/threads/${threadId}/verify-channel`, {
        method: "POST",
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const verifyData = verifyRes.ok ? await verifyRes.json() : null;
      setVerifying(false);

      if (verifyData && !verifyData.ok) {
        setActivationStatus("error");
        setActivationHint(verifyData.error || "Не удалось подключиться к каналу. Проверьте ID и права бота.");
        return;
      }
      if (verifyData && verifyData.ok && !verifyData.bot_is_admin) {
        setActivationStatus("error");
        const name = verifyData.chat_name ? ` «${verifyData.chat_name}»` : "";
        setActivationHint(`Бот не является администратором канала${name}. Назначьте бота Glosix администратором и сохраните снова.`);
        return;
      }

      // Step 3: Success
      setActivationStatus("active");
      void loadHistory();
      const channelName = verifyData?.chat_name ? ` (${verifyData.chat_name})` : "";
      if (cfg.poster_schedule.length === 0) {
        setActivationHint(`Канал${channelName} подключён. Расписание не задано — посты генерируются только по запросу в чате агента.`);
      } else {
        const parts = cfg.poster_schedule.map((s) => `${DAY_SHORT[s.day] ?? s.day} в ${s.time}`);
        setActivationHint(`Канал${channelName} подключён. Публикации по расписанию: ${parts.join(", ")}.`);
      }
    } catch (e) {
      setSaving(false);
      setVerifying(false);
      setError(e instanceof Error ? e.message : "Ошибка сохранения");
    }
  };

  const generatePost = async () => {
    setGenerating(true);
    setDraft(null);
    setDraftAction("");
    setDraftError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/generate-post`, {
        method: "POST",
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = res.ok ? await res.json() : null;
      if (!data?.ok) {
        setDraftAction("error");
        setDraftError(data?.error || "Не удалось сгенерировать пост");
      } else if (data.mode === "published") {
        setDraftAction("published");
        void loadHistory();
      } else if (data.mode === "web_draft") {
        // Show draft card in the panel — user reviews here, no DM
        setDraft({ postId: data.post_id, text: data.post_text, topic: data.topic });
      }
    } catch {
      setDraftAction("error");
      setDraftError("Ошибка при генерации поста");
    } finally {
      setGenerating(false);
    }
  };

  const handleDraftAction = async (action: "approve" | "reject" | "regen") => {
    if (!draft) return;
    setDraftAction("actioning");
    setDraftError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/draft-action`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ action, post_id: draft.postId }),
      });
      const data = res.ok ? await res.json() : null;
      if (!data?.ok) {
        setDraftAction("error");
        setDraftError(data?.error || "Ошибка");
      } else if (data.mode === "published") {
        setDraft(null);
        setDraftAction("published");
        void loadHistory();
      } else if (data.mode === "rejected") {
        setDraft(null);
        setDraftAction("rejected");
      } else if (data.mode === "web_draft") {
        setDraft({ postId: data.post_id, text: data.post_text, topic: data.topic });
        setDraftAction("");
        setEditedText("");
      }
    } catch {
      setDraftAction("error");
      setDraftError("Ошибка");
    }
  };

  const handleStartEdit = () => {
    setEditedText(draft?.text ?? "");
    setDraftAction("editing");
  };

  const handleSaveEdit = async () => {
    if (!draft) return;
    setDraftAction("actioning");
    setDraftError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/draft-action`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ action: "edit", post_id: draft.postId, text: editedText }),
      });
      const data = res.ok ? await res.json() : null;
      if (!data?.ok) {
        setDraftAction("editing");
        setDraftError(data?.error || "Ошибка сохранения");
      } else {
        setDraft({ postId: data.post_id, text: data.post_text, topic: data.topic });
        setDraftAction("");
        setEditedText("");
      }
    } catch {
      setDraftAction("editing");
      setDraftError("Ошибка");
    }
  };

  const f = !enabled;

  return (
    <div className={`poster-settings${f ? " poster-settings--disabled" : ""}`}>
      {/* Toggle header */}
      <div className="poster-settings__header">
        <span className="poster-settings__title">Постинг в канал</span>
        <label className="poster-settings__toggle">
          <input type="checkbox" checked={enabled} onChange={(e) => handleToggle(e.target.checked)} />
          <span className="poster-settings__toggle-track">
            <span className="poster-settings__toggle-thumb" />
          </span>
          <span className="poster-settings__toggle-label">{enabled ? "Включён" : "Выключен"}</span>
        </label>
      </div>

      <div className="poster-settings__body">
        {/* Channel */}
        <div className="poster-field">
          <label className="poster-field__label">
            Канал MAX <span className="poster-field__required">*</span>
          </label>
          <input
            className={`poster-field__input${!channelOk && enabled ? " poster-field__input--error" : ""}`}
            type="text"
            placeholder="@mychannel или -123456789"
            value={cfg.poster_channel_id}
            disabled={f}
            onChange={(e) => patch("poster_channel_id", e.target.value)}
          />
          <span className="poster-field__hint">Ссылка или ID канала, где бот — администратор</span>
        </div>

        {/* Topics */}
        <div className="poster-field">
          <label className="poster-field__label">
            Темы публикаций <span className="poster-field__required">*</span>
          </label>
          <textarea
            className={`poster-field__textarea${!topicsOk && enabled ? " poster-field__input--error" : ""}`}
            rows={3}
            placeholder="Новости компании; Советы и лайфхаки; Акции и скидки"
            value={cfg.poster_topics}
            disabled={f}
            onChange={(e) => patch("poster_topics", e.target.value)}
          />
          <span className="poster-field__hint">Через точку с запятой. Темы чередуются по очереди.</span>
        </div>

        {/* Tone + Length */}
        <div className="poster-field-row">
          <div className="poster-field">
            <label className="poster-field__label">Тон</label>
            <select className="poster-field__select" value={cfg.poster_tone} disabled={f} onChange={(e) => patch("poster_tone", e.target.value)}>
              <option value="official">Официальный</option>
              <option value="informal">Неформальный</option>
              <option value="expert">Экспертный</option>
              <option value="inspiring">Вдохновляющий</option>
            </select>
          </div>
          <div className="poster-field">
            <label className="poster-field__label">Длина поста</label>
            <select className="poster-field__select" value={cfg.poster_length} disabled={f} onChange={(e) => patch("poster_length", e.target.value)}>
              <option value="short">Короткий (~500 зн.)</option>
              <option value="medium">Средний (~1000 зн.)</option>
              <option value="long">Длинный (~2000 зн.)</option>
            </select>
          </div>
        </div>

        {/* Emoji + CTA */}
        <div className="poster-field-row">
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input type="checkbox" checked={cfg.poster_emoji} disabled={f} onChange={(e) => patch("poster_emoji", e.target.checked)} />
            <span>Эмодзи в постах</span>
          </label>
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input type="checkbox" checked={cfg.poster_cta} disabled={f} onChange={(e) => patch("poster_cta", e.target.checked)} />
            <span>Призыв к действию (CTA)</span>
          </label>
        </div>

        {/* Media */}
        <div className="poster-field">
          <label className="poster-field__label">Изображения</label>
          <select className="poster-field__select" value={cfg.poster_media} disabled={f} onChange={(e) => patch("poster_media", e.target.value)}>
            <option value="none">Без изображений (только текст)</option>
            <option value="manual">Прикреплять вручную при запросе</option>
            <option value="ai">Генерировать через ИИ автоматически</option>
          </select>
        </div>

        {/* Schedule slots */}
        <div className="poster-field">
          <label className="poster-field__label">Расписание публикаций</label>

          {cfg.poster_schedule.length === 0 ? (
            <div className="poster-schedule-empty">
              Не задано — ручной режим: посты только по запросу в чате агента
            </div>
          ) : (
            <div className="poster-schedule-list">
              {cfg.poster_schedule.map((slot, idx) => (
                <div key={idx} className="poster-slot">
                  <select
                    className="poster-slot__day"
                    value={slot.day}
                    disabled={f}
                    onChange={(e) => updateSlot(idx, "day", e.target.value)}
                  >
                    {DAY_OPTIONS.map((d) => (
                      <option key={d.key} value={d.key}>{d.label}</option>
                    ))}
                  </select>
                  <input
                    className="poster-slot__time"
                    type="time"
                    value={slot.time}
                    disabled={f}
                    onChange={(e) => updateSlot(idx, "time", e.target.value)}
                  />
                  {!f && (
                    <button
                      type="button"
                      className="poster-slot__remove"
                      onClick={() => removeSlot(idx)}
                      aria-label="Удалить слот"
                      title="Удалить"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {!f && (
            <button type="button" className="poster-add-slot" onClick={addSlot}>
              + Добавить время публикации
            </button>
          )}
        </div>

        {/* Timezone — only shown when schedule is set */}
        {cfg.poster_schedule.length > 0 && (
          <div className="poster-field">
            <label className="poster-field__label">Часовой пояс</label>
            <select
              className="poster-field__select"
              value={cfg.poster_timezone}
              disabled={f}
              onChange={(e) => patch("poster_timezone", e.target.value)}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>{tz.label}</option>
              ))}
            </select>
            <span className="poster-field__hint">Время публикации в вашем часовом поясе</span>
          </div>
        )}

        {/* Approval + Reflection */}
        <div className="poster-field-row">
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input type="checkbox" checked={cfg.poster_approval} disabled={f} onChange={(e) => patch("poster_approval", e.target.checked)} />
            <span>Согласование перед публикацией</span>
          </label>
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input type="checkbox" checked={cfg.poster_reflection} disabled={f} onChange={(e) => patch("poster_reflection", e.target.checked)} />
            <span>Проверка качества (рефлексия)</span>
          </label>
        </div>

        {/* Save */}
        <div className="poster-settings__footer">
          <span className="poster-settings__validation-hint">{error || validationHint}</span>
          <button
            type="button"
            className="poster-settings__save"
            disabled={!canSave || saving || verifying}
            onClick={save}
            title={validationHint || undefined}
          >
            {saving ? "Сохраняем…" : verifying ? "Проверяем канал…" : "Сохранить настройки"}
          </button>
        </div>
      </div>

      {/* Status messages */}
      {(saving || verifying) && (
        <div className="poster-status poster-status--checking">
          <span className="poster-status__spinner" />
          {verifying ? "Проверяем права бота в канале…" : "Сохраняем настройки…"}
        </div>
      )}
      {!saving && !verifying && showActiveUI && (
        <div className="poster-status poster-status--active">
          ✅ Агент активирован. {activationHint}
        </div>
      )}
      {!saving && !verifying && activationStatus === "error" && (
        <div className="poster-status poster-status--error">
          ⚠️ {activationHint}
        </div>
      )}
      {activationStatus === "inactive" && (
        <div className="poster-status poster-status--inactive">
          ⏸ Агент деактивирован. Чтобы включить — активируйте его в форме выше.
        </div>
      )}

      {/* One-time post generation */}
      {showActiveUI && (
        <div className="poster-generate">
          {/* Generate button — hidden while draft is shown */}
          {!draft && (
            <button
              type="button"
              className="poster-generate__btn"
              disabled={generating || draftAction === "actioning"}
              onClick={generatePost}
            >
              {generating ? (
                <><span className="poster-status__spinner" /> Генерируем пост…</>
              ) : (
                "✏️ Сгенерировать разовый пост"
              )}
            </button>
          )}

          {/* Status after action */}
          {!draft && draftAction === "published" && (
            <span className="poster-generate__result poster-generate__result--ok">✓ Пост опубликован в канале</span>
          )}
          {!draft && draftAction === "rejected" && (
            <span className="poster-generate__result poster-generate__result--ok" style={{color: "var(--text-muted)"}}>Пост отклонён</span>
          )}
          {!draft && draftAction === "error" && (
            <span className="poster-generate__result poster-generate__result--err">⚠️ {draftError}</span>
          )}

          {/* Draft card — inline review in mini-app */}
          {draft && (
            <div className="poster-draft">
              <div className="poster-draft__header">
                <span className="poster-draft__label">📝 Черновик — тема: <em>{draft.topic}</em></span>
                {draftAction !== "editing" && (
                  <button
                    type="button"
                    className="poster-draft__edit-toggle"
                    onClick={handleStartEdit}
                    title="Редактировать текст"
                  >
                    ✏️
                  </button>
                )}
              </div>

              {/* Edit mode: textarea */}
              {draftAction === "editing" ? (
                <div className="poster-draft__edit-area">
                  <textarea
                    className="poster-draft__textarea"
                    value={editedText}
                    rows={10}
                    autoFocus
                    onChange={(e) => setEditedText(e.target.value)}
                  />
                  {draftError && <div className="poster-draft__error">⚠️ {draftError}</div>}
                  <div className="poster-draft__edit-footer">
                    <span className="poster-draft__char-count">{editedText.length} зн.</span>
                    <div className="poster-draft__edit-btns">
                      <button type="button" className="poster-draft__btn poster-draft__btn--approve" onClick={handleSaveEdit}>
                        Сохранить
                      </button>
                      <button type="button" className="poster-draft__btn poster-draft__btn--regen" onClick={() => { setDraftAction(""); setDraftError(""); }}>
                        Отмена
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="poster-draft__text">{draft.text}</div>
              )}

              {draftAction === "error" && (
                <div className="poster-draft__error">⚠️ {draftError}</div>
              )}

              {draftAction !== "editing" && (
                <div className="poster-draft__actions">
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--approve"
                    disabled={draftAction === "actioning"}
                    onClick={() => handleDraftAction("approve")}
                  >
                    {draftAction === "actioning" ? <span className="poster-status__spinner" /> : "✅"} Опубликовать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--regen"
                    disabled={draftAction === "actioning"}
                    onClick={() => handleDraftAction("regen")}
                  >
                    🔄 Перегенерировать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--edit"
                    disabled={draftAction === "actioning"}
                    onClick={handleStartEdit}
                  >
                    ✏️ Редактировать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--reject"
                    disabled={draftAction === "actioning"}
                    onClick={() => handleDraftAction("reject")}
                  >
                    ❌ Отклонить
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Post history — shown when active */}
      {showActiveUI && (
        <div className="poster-history">
          <div className="poster-history__header">
            <span className="poster-history__title">История постов</span>
            <button type="button" className="poster-history__refresh" onClick={loadHistory} title="Обновить">
              {historyLoading ? "⟳" : "↺"}
            </button>
          </div>
          {history.length === 0 ? (
            <div className="poster-history__empty">Постов ещё нет</div>
          ) : (
            <div className="poster-history__list">
              {history.map((item) => (
                <div key={item.id} className="poster-history__item">
                  <span className={`poster-history__badge poster-history__badge--${item.status}`}>
                    {item.status === "published" ? "✅" : item.status === "rejected" ? "❌" : "📝"}
                  </span>
                  <div className="poster-history__item-body">
                    <span className="poster-history__topic">{item.topic}</span>
                    <span className="poster-history__date">{item.at.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
