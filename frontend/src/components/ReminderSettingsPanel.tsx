import { useState, useEffect, useCallback } from "react";
import { useAuthStore } from "../store/authStore";
import { useTouchThread } from "../hooks/useTouchThread";

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

const WEEKDAYS = [
  { key: "mon", label: "Понедельник" },
  { key: "tue", label: "Вторник" },
  { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" },
  { key: "fri", label: "Пятница" },
  { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" },
];

const SCHEDULE_TYPES = [
  { value: "one_time", label: "Один раз" },
  { value: "daily", label: "Ежедневно" },
  { value: "weekly", label: "Еженедельно" },
  { value: "monthly", label: "Ежемесячно" },
  { value: "quarterly", label: "Раз в квартал" },
  { value: "yearly", label: "Раз в год" },
  { value: "interval", label: "Через интервал" },
];

type ReminderItem = {
  id: string;
  name: string;
  text: string;
  schedule_text: string;
  schedule_type: string;
  time: string;
  weekday: string;
  day_of_month: number | null;
  date: string;
  interval_value: number | null;
  interval_unit: string;
  delivery_mode: string;
  max_chat_id: number | null;
  timezone: string;
  enabled: boolean;
  status: string;
  next_run_at: string | null;
  recurrence_label: string;
};

type FormState = {
  name: string;
  text: string;
  schedule_type: string;
  time: string;
  weekday: string;
  day_of_month: number;
  date: string;
  interval_value: number;
  interval_unit: string;
  delivery_mode: string;
  max_chat_id: string;
  timezone: string;
};

function tomorrowDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}

const defaultForm = (): FormState => ({
  name: "",
  text: "",
  schedule_type: "one_time",
  time: "09:00",
  weekday: "mon",
  day_of_month: 1,
  date: tomorrowDate(),
  interval_value: 30,
  interval_unit: "minutes",
  delivery_mode: "dm",
  max_chat_id: "",
  timezone: "Europe/Moscow",
});

function formatNextRun(nextRunAt: string | null): string {
  if (!nextRunAt) return "";
  try {
    const d = new Date(nextRunAt);
    return d.toLocaleString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return nextRunAt;
  }
}


// Preset time options every 30 minutes
const TIME_OPTIONS = Array.from({ length: 48 }, (_, i) => {
  const h = Math.floor(i / 2).toString().padStart(2, "0");
  const m = i % 2 === 0 ? "00" : "30";
  return `${h}:${m}`;
});

// Pre-set interval options
const INTERVAL_OPTIONS = [
  { label: "5 минут",   value: 5,  unit: "minutes" },
  { label: "10 минут",  value: 10, unit: "minutes" },
  { label: "15 минут",  value: 15, unit: "minutes" },
  { label: "30 минут",  value: 30, unit: "minutes" },
  { label: "1 час",     value: 1,  unit: "hours" },
  { label: "2 часа",    value: 2,  unit: "hours" },
  { label: "3 часа",    value: 3,  unit: "hours" },
  { label: "6 часов",   value: 6,  unit: "hours" },
  { label: "12 часов",  value: 12, unit: "hours" },
];

function ScheduleFields({
  form,
  onChange,
}: {
  form: FormState;
  onChange: (patch: Partial<FormState>) => void;
}) {
  const stype = form.schedule_type;

  // Current interval selection key for the combined select
  const intervalKey = `${form.interval_value}_${form.interval_unit}`;

  return (
    <div className="rm-schedule-fields">
      <div className="rm-field">
        <label className="rm-label">Тип расписания</label>
        <select
          className="rm-select"
          value={stype}
          onChange={(e) => onChange({ schedule_type: e.target.value })}
        >
          {SCHEDULE_TYPES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Date for one_time — native date picker (mobile friendly) */}
      {stype === "one_time" && (
        <div className="rm-field">
          <label className="rm-label">Дата</label>
          <input
            type="date"
            className="rm-input"
            value={form.date}
            onChange={(e) => onChange({ date: e.target.value })}
          />
        </div>
      )}

      {/* Time as dropdown — for all types except interval */}
      {stype !== "interval" && (
        <div className="rm-field">
          <label className="rm-label">Время</label>
          <select
            className="rm-select"
            value={TIME_OPTIONS.includes(form.time) ? form.time : form.time}
            onChange={(e) => onChange({ time: e.target.value })}
          >
            {/* Include custom value if not in presets */}
            {!TIME_OPTIONS.includes(form.time) && form.time && (
              <option value={form.time}>{form.time}</option>
            )}
            {TIME_OPTIONS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      )}

      {/* Weekday for weekly */}
      {stype === "weekly" && (
        <div className="rm-field">
          <label className="rm-label">День недели</label>
          <select
            className="rm-select"
            value={form.weekday}
            onChange={(e) => onChange({ weekday: e.target.value })}
          >
            {WEEKDAYS.map((w) => (
              <option key={w.key} value={w.key}>{w.label}</option>
            ))}
          </select>
        </div>
      )}

      {/* Day of month for monthly — select 1-31 */}
      {stype === "monthly" && (
        <div className="rm-field">
          <label className="rm-label">Число месяца</label>
          <select
            className="rm-select"
            value={form.day_of_month}
            onChange={(e) => onChange({ day_of_month: Number(e.target.value) })}
          >
            {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
              <option key={d} value={d}>{d}-е</option>
            ))}
          </select>
        </div>
      )}

      {/* Interval — single select with presets */}
      {stype === "interval" && (
        <div className="rm-field">
          <label className="rm-label">Интервал</label>
          <select
            className="rm-select"
            value={intervalKey}
            onChange={(e) => {
              const opt = INTERVAL_OPTIONS.find(
                (o) => `${o.value}_${o.unit}` === e.target.value
              );
              if (opt) onChange({ interval_value: opt.value, interval_unit: opt.unit });
            }}
          >
            {INTERVAL_OPTIONS.map((o) => (
              <option key={`${o.value}_${o.unit}`} value={`${o.value}_${o.unit}`}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}

function ReminderForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: Partial<FormState>;
  onSave: (form: FormState) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<FormState>({ ...defaultForm(), ...(initial || {}) });
  const patch = (p: Partial<FormState>) => setForm((f) => ({ ...f, ...p }));

  const canSave = form.text.trim().length > 0;

  return (
    <div className="rm-form-card">
      <div className="rm-field">
        <label className="rm-label">
          Название{" "}
          <span style={{ color: "#8fa0a8", fontWeight: 400, fontSize: "0.8em" }}>(необязательно)</span>
        </label>
        <input
          type="text"
          className="rm-input"
          placeholder="Например: Звонок клиенту, Оплата счёта..."
          value={form.name}
          onChange={(e) => patch({ name: e.target.value })}
          maxLength={60}
        />
      </div>
      <div className="rm-field">
        <label className="rm-label">Текст напоминания *</label>
        <textarea
          className="rm-textarea"
          rows={2}
          placeholder="Например: Позвонить клиенту, Оплатить счёт..."
          value={form.text}
          onChange={(e) => patch({ text: e.target.value })}
        />
      </div>

      <ScheduleFields form={form} onChange={patch} />

      <div className="rm-field">
        <label className="rm-label">Часовой пояс</label>
        <select
          className="rm-select"
          value={form.timezone}
          onChange={(e) => patch({ timezone: e.target.value })}
        >
          {TIMEZONES.map((tz) => (
            <option key={tz.value} value={tz.value}>{tz.label}</option>
          ))}
        </select>
      </div>

      <div className="rm-field">
        <label className="rm-label">Куда отправить</label>
        <div className="rm-radio-group">
          <label className="rm-radio">
            <input
              type="radio"
              name="delivery_mode"
              value="dm"
              checked={form.delivery_mode === "dm"}
              onChange={() => patch({ delivery_mode: "dm" })}
            />
            В личный чат с ботом
          </label>
          <label className="rm-radio">
            <input
              type="radio"
              name="delivery_mode"
              value="group"
              checked={form.delivery_mode === "group"}
              onChange={() => patch({ delivery_mode: "group" })}
            />
            В группу MAX
          </label>
        </div>
      </div>

      {form.delivery_mode === "group" && (
        <div className="rm-field">
          <label className="rm-label">ID группы (например: -1234567890)</label>
          <input
            type="text"
            className="rm-input"
            placeholder="-1234567890"
            value={form.max_chat_id}
            onChange={(e) => patch({ max_chat_id: e.target.value })}
          />
        </div>
      )}

      <div className="rm-form-actions">
        <button
          className="rm-btn rm-btn--primary"
          disabled={!canSave || saving}
          onClick={() => onSave(form)}
        >
          {saving ? "Сохраняем..." : "Сохранить"}
        </button>
        <button className="rm-btn rm-btn--ghost" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </div>
  );
}

function ReminderCard({
  item,
  onDelete,
  onToggle,
  onEdit,
}: {
  item: ReminderItem;
  onDelete: (id: string) => void;
  onToggle: (id: string, enabled: boolean) => void;
  onEdit: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  const statusIcon = item.enabled
    ? "🟢"
    : item.status === "cancelled"
    ? "🚫"
    : "⏸";

  return (
    <div className={`rm-card ${item.enabled ? "" : "rm-card--disabled"}`}>
      <div className="rm-card-header">
        <span className="rm-card-status">{statusIcon}</span>
        <div className="rm-card-info">
          <div className="rm-card-text">
            {item.name
              ? item.name
              : item.text
                ? (item.text.length > 30 ? item.text.slice(0, 30) + "…" : item.text)
                : "—"}
          </div>
          <div className="rm-card-meta">
            <span className="rm-tag">{item.recurrence_label}</span>
            {item.schedule_text && (
              <span className="rm-card-schedule">{item.schedule_text}</span>
            )}
            {item.next_run_at && item.enabled && item.recurrence_label !== "Разово" && (
              <span className="rm-card-next">
                Следующее: {formatNextRun(item.next_run_at)}
              </span>
            )}
          </div>
        </div>
        <div className="rm-card-actions">
          <button
            className={`rm-toggle ${item.enabled ? "rm-toggle--on" : ""}`}
            title={item.enabled ? "Выключить" : "Включить"}
            onClick={() => onToggle(item.id, !item.enabled)}
          >
            {item.enabled ? "Вкл" : "Выкл"}
          </button>
          <button
            className="rm-icon-btn"
            title="Редактировать"
            onClick={() => onEdit(item.id)}
          >
            ✏️
          </button>
          {!confirming ? (
            <button
              className="rm-icon-btn rm-icon-btn--danger"
              title="Удалить"
              onClick={() => setConfirming(true)}
            >
              🗑
            </button>
          ) : (
            <>
              <button
                className="rm-btn rm-btn--danger rm-btn--sm"
                onClick={() => onDelete(item.id)}
              >
                Удалить
              </button>
              <button
                className="rm-btn rm-btn--ghost rm-btn--sm"
                onClick={() => setConfirming(false)}
              >
                Отмена
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function ReminderSettingsPanel({ threadId }: { threadId: string }) {
  const token = useAuthStore((s) => s.token);
  const touchThread = useTouchThread(threadId, token);
  const [reminders, setReminders] = useState<ReminderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/reminders`, { headers });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setReminders(data.reminders || []);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, [threadId, token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form: FormState) => {
    setSaving(true);
    setActionError("");
    try {
      const body = {
        name: form.name.trim() || null,
        text: form.text,
        schedule_type: form.schedule_type,
        time: form.time,
        weekday: form.weekday,
        day_of_month: form.day_of_month,
        date: form.date,
        interval_value: form.interval_value,
        interval_unit: form.interval_unit,
        delivery_mode: form.delivery_mode,
        max_chat_id: form.delivery_mode === "group" && form.max_chat_id ? Number(form.max_chat_id) : null,
        timezone: form.timezone,
      };

      const url = editingId
        ? `${API_BASE}/api/agent/threads/${threadId}/reminders/${editingId}`
        : `${API_BASE}/api/agent/threads/${threadId}/reminders`;
      const method = editingId ? "PATCH" : "POST";

      const res = await fetch(url, { method, headers, body: JSON.stringify(body) });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }

      setShowForm(false);
      setEditingId(null);
      await load();
    } catch (e: any) {
      setActionError(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    setActionError("");
    try {
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/reminders/${id}`,
        { method: "PATCH", headers, body: JSON.stringify({ enabled }) }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }
      await load();
    } catch (e: any) {
      setActionError(String(e.message || e));
    }
  };

  const handleDelete = async (id: string) => {
    setActionError("");
    try {
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/reminders/${id}`,
        { method: "DELETE", headers }
      );
      if (!res.ok) throw new Error(await res.text());
      await load();
    } catch (e: any) {
      setActionError(String(e.message || e));
    }
  };

  const handleEdit = (id: string) => {
    const item = reminders.find((r) => r.id === id);
    if (!item) return;
    setEditingId(id);
    setShowForm(true);
    setActionError("");
  };

  const editingItem = editingId ? reminders.find((r) => r.id === editingId) : null;
  const editingInitial: Partial<FormState> | undefined = editingItem
    ? {
        name: editingItem.name || "",
        text: editingItem.text,
        schedule_type: editingItem.schedule_type || "one_time",
        time: editingItem.time || "09:00",
        weekday: editingItem.weekday || "mon",
        day_of_month: editingItem.day_of_month ?? 1,
        date: editingItem.date || "",
        interval_value: editingItem.interval_value ?? 30,
        interval_unit: editingItem.interval_unit || "minutes",
        delivery_mode: editingItem.delivery_mode || "dm",
        // Всегда передаём max_chat_id — иначе при редактировании группового напоминания поле пустое
        max_chat_id: editingItem.max_chat_id != null ? String(editingItem.max_chat_id) : "",
        timezone: editingItem.timezone || "Europe/Moscow",
      }
    : undefined;

  return (
    <div className="rm-panel">
      <div className="rm-panel-header">
        <h3 className="rm-panel-title">Напоминания</h3>
        {!showForm && (
          <button
            className="rm-btn rm-btn--primary"
            onClick={() => { void touchThread(); setShowForm(true); setEditingId(null); setActionError(""); }}
          >
            + Добавить
          </button>
        )}
      </div>

      {actionError && (
        <div className="rm-error">{actionError}</div>
      )}

      {showForm && (
        <ReminderForm
          initial={editingInitial}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditingId(null); setActionError(""); }}
          saving={saving}
        />
      )}

      {loading ? (
        <div className="rm-loading">Загрузка...</div>
      ) : error ? (
        <div className="rm-error">{error}</div>
      ) : reminders.length === 0 && !showForm ? (
        <div className="rm-empty">
          <div className="rm-empty-icon">🔔</div>
          <div className="rm-empty-text">Нет напоминаний</div>
          <div className="rm-empty-hint">Нажмите «+ Добавить», чтобы создать первое напоминание</div>
        </div>
      ) : (
        <div className="rm-list">
          {reminders.map((item) => (
            <ReminderCard
              key={item.id}
              item={item}
              onDelete={handleDelete}
              onToggle={handleToggle}
              onEdit={handleEdit}
            />
          ))}
        </div>
      )}
    </div>
  );
}
