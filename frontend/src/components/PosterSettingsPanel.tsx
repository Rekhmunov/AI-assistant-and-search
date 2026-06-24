import { useState, useEffect, useRef } from "react";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "";

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
  const [activationStatus, setActivationStatus] = useState<"idle" | "active" | "inactive" | "error">("idle");
  const [activationHint, setActivationHint] = useState("");
  const [error, setError] = useState("");
  const initDone = useRef(false);

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
      {!saving && !verifying && activationStatus === "active" && (
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
    </div>
  );
}
