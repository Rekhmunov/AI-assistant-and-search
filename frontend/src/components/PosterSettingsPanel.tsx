import { useState, useEffect } from "react";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "";

const DAYS = [
  { key: "mon", label: "Пн" },
  { key: "tue", label: "Вт" },
  { key: "wed", label: "Ср" },
  { key: "thu", label: "Чт" },
  { key: "fri", label: "Пт" },
  { key: "sat", label: "Сб" },
  { key: "sun", label: "Вс" },
];

type PosterConfig = {
  poster_channel_id: string;
  poster_topics: string;
  poster_tone: string;
  poster_emoji: boolean;
  poster_length: string;
  poster_cta: boolean;
  poster_media: string;
  poster_days: string[];
  poster_time: string;
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
  poster_days: [],
  poster_time: "10:00",
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
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!initialConfig) return;
    setCfg({
      poster_channel_id: String(initialConfig.poster_channel_id ?? ""),
      poster_topics: String(initialConfig.poster_topics ?? ""),
      poster_tone: String(initialConfig.poster_tone ?? "official"),
      poster_emoji: initialConfig.poster_emoji !== false,
      poster_length: String(initialConfig.poster_length ?? "medium"),
      poster_cta: Boolean(initialConfig.poster_cta),
      poster_media: String(initialConfig.poster_media ?? "none"),
      poster_days: Array.isArray(initialConfig.poster_days) ? (initialConfig.poster_days as string[]) : [],
      poster_time: String(initialConfig.poster_time ?? "10:00"),
      poster_approval: initialConfig.poster_approval !== false,
      poster_reflection: initialConfig.poster_reflection !== false,
    });
  }, [initialConfig]);

  const patch = <K extends keyof PosterConfig>(key: K, value: PosterConfig[K]) =>
    setCfg((c) => ({ ...c, [key]: value }));

  const toggleDay = (day: string) => {
    if (!enabled) return;
    const days = cfg.poster_days.includes(day)
      ? cfg.poster_days.filter((d) => d !== day)
      : [...cfg.poster_days, day];
    patch("poster_days", days);
  };

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error("Не удалось сохранить");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setSaving(false);
    }
  };

  const f = !enabled; // fields disabled when toggle is off

  return (
    <div className={`poster-settings${f ? " poster-settings--disabled" : ""}`}>
      {/* Toggle */}
      <div className="poster-settings__header">
        <span className="poster-settings__title">Постинг в канал</span>
        <label className="poster-settings__toggle">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onToggle(e.target.checked)}
          />
          <span className="poster-settings__toggle-track">
            <span className="poster-settings__toggle-thumb" />
          </span>
          <span className="poster-settings__toggle-label">{enabled ? "Включён" : "Выключен"}</span>
        </label>
      </div>

      {/* Body — always visible, but fields disabled when off */}
      <div className="poster-settings__body">
        {/* Channel */}
        <div className="poster-field">
          <label className="poster-field__label">Канал MAX</label>
          <input
            className="poster-field__input"
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
          <label className="poster-field__label">Темы публикаций</label>
          <textarea
            className="poster-field__textarea"
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
            <select
              className="poster-field__select"
              value={cfg.poster_tone}
              disabled={f}
              onChange={(e) => patch("poster_tone", e.target.value)}
            >
              <option value="official">Официальный</option>
              <option value="informal">Неформальный</option>
              <option value="expert">Экспертный</option>
              <option value="inspiring">Вдохновляющий</option>
            </select>
          </div>
          <div className="poster-field">
            <label className="poster-field__label">Длина поста</label>
            <select
              className="poster-field__select"
              value={cfg.poster_length}
              disabled={f}
              onChange={(e) => patch("poster_length", e.target.value)}
            >
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
          <select
            className="poster-field__select"
            value={cfg.poster_media}
            disabled={f}
            onChange={(e) => patch("poster_media", e.target.value)}
          >
            <option value="none">Без изображений (только текст)</option>
            <option value="manual">Прикреплять вручную при запросе</option>
            <option value="ai">Генерировать через ИИ автоматически</option>
          </select>
        </div>

        {/* Schedule */}
        <div className="poster-field">
          <label className="poster-field__label">Дни публикации</label>
          <div className="poster-days">
            {DAYS.map((d) => (
              <button
                key={d.key}
                type="button"
                disabled={f}
                className={`poster-day${cfg.poster_days.includes(d.key) ? " poster-day--active" : ""}${f ? " poster-day--disabled" : ""}`}
                onClick={() => toggleDay(d.key)}
              >
                {d.label}
              </button>
            ))}
          </div>
          {!f && cfg.poster_days.length === 0 && (
            <span className="poster-field__hint">Не выбрано — только по ручному запросу</span>
          )}
        </div>

        {cfg.poster_days.length > 0 && (
          <div className="poster-field">
            <label className="poster-field__label">Время публикации</label>
            <input
              className="poster-field__input poster-field__input--time"
              type="time"
              value={cfg.poster_time}
              disabled={f}
              onChange={(e) => patch("poster_time", e.target.value)}
            />
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
          {error && <span className="poster-settings__error">{error}</span>}
          <button
            type="button"
            className={`poster-settings__save${saved ? " poster-settings__save--ok" : ""}`}
            disabled={saving || f}
            onClick={save}
          >
            {saved ? "✓ Сохранено" : saving ? "Сохраняем…" : "Сохранить настройки"}
          </button>
        </div>
      </div>
    </div>
  );
}
