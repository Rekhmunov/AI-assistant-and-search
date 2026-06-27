import { useState, useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "../store/authStore";
import { ProUpgradeModal } from "./ProUpgradeModal";

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

type HistoryItem = { id: string; topic: string; status: string; at: string; text?: string };
type HistoryPage = { items: HistoryItem[]; total: number; page: number; pages: number };

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
  poster_topics: string;        // legacy fallback
  poster_topic_list: { text: string; search: boolean }[];  // {text, search} per topic
  poster_topic_mode: string;    // "random" | "no_repeat" | "sequential" | "priority"
  poster_tone: string;
  poster_emoji: boolean;
  poster_length: string;
  poster_cta: boolean;
  poster_media: string;
  poster_schedule: ScheduleSlot[];
  poster_timezone: string;
  poster_approval: boolean;
  poster_reflection: boolean;
  // Content quality
  poster_format: string;
  poster_hook: string;
  poster_audience: string;
  poster_cta_type: string;
  // Custom chip lists per field (user can add/remove)
  poster_format_chips: string[];
  poster_hook_chips: string[];
  poster_audience_chips: string[];
  poster_cta_chips: string[];
};

const DEFAULTS: PosterConfig = {
  poster_channel_id: "",
  poster_topics: "",
  poster_topic_list: [{ text: "", search: false }],
  poster_topic_mode: "no_repeat",
  poster_tone: "official",
  poster_emoji: true,
  poster_length: "medium",
  poster_cta: false,
  poster_media: "none",
  poster_schedule: [],
  poster_timezone: "Europe/Moscow",
  poster_approval: true,
  poster_reflection: true,
  poster_format: "auto",
  poster_hook: "auto",
  poster_audience: "",
  poster_cta_type: "none",
  poster_format_chips: ["Новость + вывод", "Топ-5 список", "How-to", "Вопрос аудитории", "Кейс", "Мнение"],
  poster_hook_chips: ["Провокация", "Вопрос", "Неожиданная цифра", "Начало истории"],
  poster_audience_chips: [],
  poster_cta_chips: ["Вопрос для комментариев", "Сохранить пост", "Переслать коллегам", "Подписаться", "Ссылка в описании"],
};

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
};

// ─── Reusable multi-select chips field ──────────────────────────────────────
function ChipsField({
  label, value, chips, disabled, hint, onChange, onChipsChange,
}: {
  label: string; value: string; chips: string[]; disabled?: boolean;
  hint?: string; onChange: (v: string) => void; onChipsChange: (chips: string[]) => void;
}) {
  const [addingNew, setAddingNew] = useState(false);
  const [newChip, setNewChip] = useState("");
  const selected = new Set(value ? value.split(",").map((v) => v.trim()).filter(Boolean) : []);

  const toggleChip = (chip: string) => {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(chip)) next.delete(chip); else next.add(chip);
    onChange(Array.from(next).join(", "));
  };

  const deleteChip = (chip: string) => {
    onChipsChange(chips.filter((c) => c !== chip));
    const next = new Set(selected); next.delete(chip);
    onChange(Array.from(next).join(", "));
  };

  const addChip = () => {
    const t = newChip.trim();
    if (!t || chips.includes(t)) { setAddingNew(false); setNewChip(""); return; }
    onChipsChange([...chips, t]);
    const next = new Set(selected); next.add(t);
    onChange(Array.from(next).join(", "));
    setNewChip(""); setAddingNew(false);
  };

  return (
    <div className="poster-field">
      <label className="poster-field__label">{label}</label>
      <input className="poster-field__input" type="text" disabled={disabled}
        placeholder="Введите значение или выберите ниже" value={value}
        onChange={(e) => onChange(e.target.value)} />
      <div className="poster-quick-chips">
        {chips.map((chip) => (
          <span key={chip} className={`poster-chip-wrap${disabled ? " poster-chip-wrap--disabled" : ""}`}>
            <button type="button" disabled={disabled}
              className={`poster-quick-chip${selected.has(chip) ? " poster-quick-chip--active" : ""}`}
              onClick={() => toggleChip(chip)}>{chip}</button>
            {!disabled && (
              <button type="button" className="poster-chip-delete"
                onClick={() => deleteChip(chip)} title="Удалить вариант">×</button>
            )}
          </span>
        ))}
        {!disabled && (addingNew ? (
          <span className="poster-chip-add-form">
            <input autoFocus className="poster-chip-add-input" type="text"
              value={newChip} placeholder="Новый вариант"
              onChange={(e) => setNewChip(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addChip(); if (e.key === "Escape") { setAddingNew(false); setNewChip(""); }}} />
            <button type="button" className="poster-chip-add-confirm" onClick={addChip}>✓</button>
            <button type="button" className="poster-chip-add-cancel" onClick={() => { setAddingNew(false); setNewChip(""); }}>✕</button>
          </span>
        ) : (
          <button type="button" className="poster-quick-chip poster-chip-add-btn"
            onClick={() => setAddingNew(true)}>+ Добавить</button>
        ))}
      </div>
      {hint && <span className="poster-field__hint">{hint}</span>}
    </div>
  );
}

export function PosterSettingsPanel({ threadId, initialConfig, enabled, onToggle }: Props) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const isFree = !user || user.plan !== "pro";
  const [imageLimitModal, setImageLimitModal] = useState(false);
  const [approvalConfirmModal, setApprovalConfirmModal] = useState(false);
  const [cfg, setCfg] = useState<PosterConfig>({ ...DEFAULTS });
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyStep, setVerifyStep] = useState<"channel" | "admin" | "">(""); 
  const [generating, setGenerating] = useState(false);
  const [draft, setDraft] = useState<{ postId: string; text: string; topic: string; imageUrl?: string; fromCelery?: boolean } | null>(null);
  // Each entry: { url: base64/blob preview, fileId: backend file_id or null }
  const [draftImages, setDraftImages] = useState<{ url: string; fileId: string | null }[]>([]);
  const [imageRegenLoading, setImageRegenLoading] = useState(false);
  const [imageUploadLoading, setImageUploadLoading] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [draftAction, setDraftAction] = useState<"" | "actioning" | "editing" | "published" | "rejected" | "error">("");
  const [draftError, setDraftError] = useState("");
  const [editedText, setEditedText] = useState("");
  const [activationStatus, setActivationStatus] = useState<"idle" | "active" | "inactive" | "error">("idle");
  const [activationHint, setActivationHint] = useState("");
  const [error, setError] = useState("");
  const [historyPage, setHistoryPage] = useState<HistoryPage | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [historyCurrentPage, setHistoryCurrentPage] = useState(1);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const HISTORY_PER_PAGE = 10;
  const initDone = useRef(false);

  // If agent already configured (has channel), show active UI without requiring re-save
  const isConfigured = Boolean(
    (initialConfig?.poster_channel_id as string | undefined)?.trim()
  );
  const showActiveUI = activationStatus === "active" || (isConfigured && enabled && activationStatus === "idle");

  const loadHistory = useCallback(async (page?: number, search?: string) => {
    if (!showActiveUI) return;
    const p = page ?? historyCurrentPage;
    const s = search ?? historySearch;
    setHistoryLoading(true);
    try {
      const qs = new URLSearchParams({ page: String(p), per_page: String(HISTORY_PER_PAGE) });
      if (s.trim()) qs.set("search", s.trim());
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/post-history?${qs}`,
        { credentials: "include", headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (res.ok) {
        const data = await res.json();
        setHistoryPage(data);
        setSelectedIds(new Set());
      }
    } catch { /* silent */ } finally {
      setHistoryLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, token, showActiveUI, historyCurrentPage, historySearch, HISTORY_PER_PAGE]);

  const handleHistorySearch = (val: string) => {
    setHistorySearch(val);
    setHistoryCurrentPage(1);
    void loadHistory(1, val);
  };

  const handleHistoryPage = (p: number) => {
    setHistoryCurrentPage(p);
    void loadHistory(p);
  };

  const deleteHistoryItem = async (id: string) => {
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/post-history/${id}`, {
      method: "DELETE",
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    void loadHistory();
  };

  const deleteSelected = async () => {
    if (selectedIds.size === 0) return;
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/post-history/clear`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ ids: Array.from(selectedIds) }),
    });
    void loadHistory(1);
  };

  const clearAllHistory = async () => {
    if (!window.confirm("Очистить всю историю постов?")) return;
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/post-history/clear`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ all: true }),
    });
    setHistoryPage(null);
    setSelectedIds(new Set());
  };

  const toggleExpand = (id: string) =>
    setExpandedIds((prev) => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  const useAsBase = async (item: HistoryItem) => {
    if (!item.text) return;
    setDraftAction("");
    setDraftError("");
    setDraftImages([]);
    // Show optimistic draft immediately
    setDraft({ postId: `pending-${item.id}`, text: item.text, topic: item.topic });
    try {
      const data = await callDraftAction({
        action: "use_as_base",
        post_id: "",           // not used for this action
        text: item.text,
        topic: item.topic,
      });
      if (data?.ok && data.post_id) {
        setDraft({ postId: data.post_id, text: data.post_text ?? item.text, topic: data.topic ?? item.topic });
        // Auto-load AI image in background if configured
        if (data.wants_ai_image) {
          setImageRegenLoading(true);
          try {
            const imgData = await callDraftAction({ action: "regen_image", post_id: data.post_id });
            if (imgData?.ok && imgData.image_url) {
              setDraftImages([{ url: imgData.image_url, fileId: imgData.file_id ?? null }]);
            }
          } finally {
            setImageRegenLoading(false);
          }
        }
      } else {
        setDraftError(data?.error || "Не удалось создать черновик");
        setDraft(null);
      }
    } catch {
      setDraftError("Ошибка при создании черновика");
      setDraft(null);
    }
  };

  const checkPendingDraft = useCallback(async () => {
    if (!showActiveUI) return;
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/pending-draft`, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.draft && (!draft || draft.postId !== data.draft.post_id)) {
        // New Celery draft arrived — show it (marks as fromCelery so polling can clear it)
        setDraft({ postId: data.draft.post_id, text: data.draft.text, topic: data.draft.topic, fromCelery: true });
        setDraftAction("");
        setDraftError("");
      } else if (!data.draft && draft?.fromCelery && draftAction !== "published" && draftAction !== "rejected") {
        // Only clear Celery drafts via polling (not locally-generated ones — avoids race condition)
        setDraft(null);
        void loadHistory();
      }
    } catch { /* silent */ }
  }, [threadId, token, showActiveUI, draft, draftAction, loadHistory]);

  // On mount: if already configured → restore status and load history + start polling
  useEffect(() => {
    if (!isConfigured || !enabled) return;
    void loadHistory();
    // Rebuild activation hint from saved schedule
    const savedSchedule = (initialConfig?.poster_schedule ?? []) as ScheduleSlot[];
    if (savedSchedule.length === 0) {
      setActivationHint("Расписание не задано — посты по запросу в чате агента.");
    } else {
      const parts = savedSchedule.map((s) => `${DAY_SHORT[s.day] ?? s.day} в ${s.time}`);
      setActivationHint(`Публикации по расписанию: ${parts.join(", ")}.`);
    }
    setActivationStatus("active");
    // Check immediately + poll every 30s for pending drafts from Celery
    void checkPendingDraft();
    pollRef.current = setInterval(() => { void checkPendingDraft(); }, 30000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
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

    // Load topic list: support {text,search} objects, plain strings, and legacy
    type TopicObj = { text: string; search: boolean };
    let topicList: TopicObj[] = [];
    const rawList = initialConfig.poster_topic_list as unknown[];
    if (Array.isArray(rawList) && rawList.length > 0) {
      topicList = rawList.map((t) => {
        if (t && typeof t === "object" && "text" in t) {
          return { text: String((t as { text: string }).text || ""), search: Boolean((t as { search?: boolean }).search) };
        }
        return { text: String(t || "").trim(), search: false };
      }).filter((t) => t.text);
    } else if (initialConfig.poster_topics) {
      topicList = String(initialConfig.poster_topics).split(/[;,\n]/).map((t) => ({ text: t.trim(), search: false })).filter((t) => t.text);
    }
    if (topicList.length === 0) topicList = [{ text: "", search: false }];

    setCfg({
      poster_channel_id: String(initialConfig.poster_channel_id ?? ""),
      poster_topics: String(initialConfig.poster_topics ?? ""),
      poster_topic_list: topicList,
      poster_topic_mode: String(initialConfig.poster_topic_mode ?? "no_repeat"),
      poster_tone: String(initialConfig.poster_tone ?? "official"),
      poster_emoji: initialConfig.poster_emoji !== false,
      poster_length: String(initialConfig.poster_length ?? "medium"),
      poster_cta: Boolean(initialConfig.poster_cta),
      poster_media: String(initialConfig.poster_media ?? "none"),
      poster_schedule: schedule,
      poster_timezone: String(initialConfig.poster_timezone ?? "Europe/Moscow"),
      poster_approval: initialConfig.poster_approval !== false,
      poster_reflection: initialConfig.poster_reflection !== false,
      poster_format: String(initialConfig.poster_format ?? "auto"),
      poster_hook: String(initialConfig.poster_hook ?? "auto"),
      poster_audience: String(initialConfig.poster_audience ?? ""),
      poster_cta_type: String(initialConfig.poster_cta_type ?? "none"),
      poster_format_chips: Array.isArray(initialConfig.poster_format_chips)
        ? initialConfig.poster_format_chips as string[]
        : DEFAULTS.poster_format_chips,
      poster_hook_chips: Array.isArray(initialConfig.poster_hook_chips)
        ? initialConfig.poster_hook_chips as string[]
        : DEFAULTS.poster_hook_chips,
      poster_audience_chips: Array.isArray(initialConfig.poster_audience_chips)
        ? initialConfig.poster_audience_chips as string[]
        : DEFAULTS.poster_audience_chips,
      poster_cta_chips: Array.isArray(initialConfig.poster_cta_chips)
        ? initialConfig.poster_cta_chips as string[]
        : DEFAULTS.poster_cta_chips,
    });
  }, [initialConfig]);

  const patch = <K extends keyof PosterConfig>(key: K, value: PosterConfig[K]) =>
    setCfg((c) => ({ ...c, [key]: value }));

  // Schedule slot operations
  // Topic list operations
  const addTopic = () => {
    if (cfg.poster_topic_list.length >= 20) return;
    patch("poster_topic_list", [...cfg.poster_topic_list, { text: "", search: false }]);
  };
  const updateTopic = (idx: number, text: string) => {
    const list = cfg.poster_topic_list.map((t, i) => i === idx ? { ...t, text } : t);
    patch("poster_topic_list", list);
  };
  const toggleTopicSearch = (idx: number) => {
    const list = cfg.poster_topic_list.map((t, i) => i === idx ? { ...t, search: !t.search } : t);
    patch("poster_topic_list", list);
  };
  const removeTopic = (idx: number) => {
    const list = cfg.poster_topic_list.filter((_, i) => i !== idx);
    patch("poster_topic_list", list.length > 0 ? list : [{ text: "", search: false }]);
  };
  const moveTopic = (idx: number, dir: -1 | 1) => {
    const list = [...cfg.poster_topic_list];
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= list.length) return;
    [list[idx], list[newIdx]] = [list[newIdx], list[idx]];
    patch("poster_topic_list", list);
  };

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

  const persistEnabled = async (val: boolean) => {
    try {
      await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ poster_enabled: val }),
      });
    } catch { /* silent — UI state takes priority */ }
  };

  const handleToggle = (val: boolean) => {
    onToggle(val);
    // Always persist toggle change immediately to DB
    void persistEnabled(val);
    if (!val) {
      setActivationStatus("inactive");
      setError("");
    } else if (activationStatus !== "active") {
      setActivationStatus("idle");
    }
  };

  // Validation
  const channelOk = cfg.poster_channel_id.trim() !== "";
  const topicsOk = cfg.poster_topic_list.some((t) => t.text.trim() !== "");
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
      // Step 1: Save config (always include poster_enabled so toggle persists)
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ ...cfg, poster_enabled: enabled }),
      });
      if (!res.ok) throw new Error("Не удалось сохранить настройки");
      setSaving(false);

      // Step 2: Verify channel admin status
      setVerifying(true);
      setVerifyStep("channel");
      // Small delay so user sees the step
      await new Promise((r) => setTimeout(r, 400));
      setVerifyStep("admin");
      const verifyRes = await fetch(`${API_BASE}/api/agent/threads/${threadId}/verify-channel`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        // Pass channel_id in body so verify-channel can save it (PATCH blocks this key)
        body: JSON.stringify({ channel_id: cfg.poster_channel_id }),
      });
      const verifyData = verifyRes.ok ? await verifyRes.json() : null;
      setVerifying(false);
      setVerifyStep("");

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

      // Step 3: Success — persist enabled state so it survives page reload
      void persistEnabled(true);
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
      setVerifyStep("");
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
        // Show draft card immediately (text is ready, image may not be yet)
        setDraft({ postId: data.post_id, text: data.post_text, topic: data.topic });
        setDraftImages([]);
        setGenerating(false);  // unlock UI immediately

        // Auto-generate AI image in background if configured
        if (data.wants_ai_image) {
          setImageRegenLoading(true);
          try {
            const imgData = await callDraftAction({ action: "regen_image", post_id: data.post_id });
            if (imgData?.ok && imgData.image_url) {
              setDraftImages([{ url: imgData.image_url, fileId: imgData.file_id ?? null }]);
            }
          } finally {
            setImageRegenLoading(false);
          }
        }
        return; // early return to skip the outer finally setGenerating(false)
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
        // Text regenerated — show new draft immediately, then load image in background
        setDraft({ postId: data.post_id, text: data.post_text, topic: data.topic });
        setDraftImages([]);
        setDraftAction("");
        setEditedText("");

        if (data.wants_ai_image) {
          setImageRegenLoading(true);
          try {
            const imgData = await callDraftAction({ action: "regen_image", post_id: data.post_id });
            if (imgData?.ok && imgData.image_url) {
              setDraftImages([{ url: imgData.image_url, fileId: imgData.file_id ?? null }]);
            }
          } finally {
            setImageRegenLoading(false);
          }
        }
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

  const callDraftAction = useCallback(async (body: Record<string, unknown>) => {
    const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/draft-action`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    return res.ok ? res.json() : null;
  }, [threadId, token]);

  const handleRegenImage = async () => {
    if (!draft) return;
    if (draftImages.length >= 4) {
      setDraftError("Максимум 4 фото. Удалите одно, чтобы добавить новое.");
      return;
    }
    setImageRegenLoading(true);
    setDraftError("");
    try {
      const data = await callDraftAction({ action: "regen_image", post_id: draft.postId });
      if (data?.ok && data.image_url) {
        // ADD to existing images (do not replace)
        setDraftImages((prev) => [...prev, { url: data.image_url, fileId: data.file_id ?? null }].slice(0, 4));
      } else {
        // For Free users hitting image generation limit — show upgrade modal
        const errMsg = data?.error || "";
        if (isFree && (errMsg.includes("лимит") || errMsg.includes("limit") || errMsg.includes("Pro"))) {
          setImageLimitModal(true);
        } else {
          setDraftError(errMsg || "Не удалось сгенерировать изображение");
        }
      }
    } finally {
      setImageRegenLoading(false);
    }
  };

  const handleUploadImages = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!draft || !e.target.files) return;
    const allFiles = Array.from(e.target.files);
    e.target.value = "";

    const available = 4 - draftImages.length;
    if (available <= 0) {
      setDraftError("Достигнут лимит 4 фото. Удалите одно, чтобы загрузить новое.");
      return;
    }

    const files = allFiles.slice(0, available);
    if (allFiles.length > available) {
      setDraftError(`Добавлено только ${files.length} из ${allFiles.length} фото — лимит 4.`);
    } else {
      setDraftError("");
    }

    setImageUploadLoading(true);
    try {
      for (const file of files) {
        // Build preview first (fast, no network)
        const dataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = (ev) => resolve(ev.target?.result as string);
          reader.readAsDataURL(file);
        });

        const formData = new FormData();
        formData.append("file", file);
        const uploadRes = await fetch(`${API_BASE}/api/files/upload`, {
          method: "POST",
          credentials: "include",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        });
        if (!uploadRes.ok) {
          const errBody = await uploadRes.json().catch(() => ({}));
          const errMsg = errBody?.detail || `HTTP ${uploadRes.status}`;
          console.error("[poster upload] file upload failed:", errMsg, uploadRes.status);
          setDraftError(`Не удалось загрузить файл: ${errMsg}`);
          continue;
        }
        const uploadData = await uploadRes.json();
        const fileId = String(uploadData?.id || "").trim();
        console.info("[poster upload] file uploaded, fileId=", fileId, "post_id=", draft.postId);
        if (!fileId) {
          setDraftError("Ошибка: сервер не вернул ID файла");
          continue;
        }

        // Register file_id in backend draft (so it's included at publish time)
        const addData = await callDraftAction({ action: "add_image", post_id: draft.postId, file_id: fileId });
        console.info("[poster upload] add_image result:", addData);
        if (addData?.ok) {
          setDraftImages((prev) => [...prev, { url: dataUrl, fileId }].slice(0, 4));
        } else {
          setDraftError(addData?.error || "Не удалось добавить фото к черновику");
        }
      }
    } finally {
      setImageUploadLoading(false);
    }
  };

  const handleRemoveImage = async (idx: number) => {
    if (!draft) return;
    const item = draftImages[idx];
    // Remove locally immediately (optimistic)
    setDraftImages((prev) => prev.filter((_, i) => i !== idx));
    setDraftError("");
    // Sync removal with backend if we know the file_id
    if (item?.fileId) {
      await callDraftAction({ action: "remove_image", post_id: draft.postId, file_id: item.fileId }).catch(() => null);
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

        {/* Topics — multiple fields */}
        <div className="poster-field">
          <label className="poster-field__label">
            Темы публикаций <span className="poster-field__required">*</span>
          </label>
          <div className="poster-topic-list">
            {cfg.poster_topic_list.map((topic, idx) => (
              <div key={idx} className="poster-topic-row">
                <div className="poster-topic-order">
                  <button type="button" className="poster-topic-arrow" disabled={f || idx === 0}
                    onClick={() => moveTopic(idx, -1)} title="Вверх">↑</button>
                  <button type="button" className="poster-topic-arrow" disabled={f || idx === cfg.poster_topic_list.length - 1}
                    onClick={() => moveTopic(idx, 1)} title="Вниз">↓</button>
                </div>
                <textarea
                  className={`poster-field__input poster-topic-input poster-topic-textarea${!topic.text.trim() && enabled ? " poster-field__input--error" : ""}`}
                  placeholder={`Тема ${idx + 1}`}
                  value={topic.text}
                  disabled={f}
                  rows={1}
                  onChange={(e) => {
                    updateTopic(idx, e.target.value);
                    // Auto-grow: reset then set to scrollHeight
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                  }}
                  onFocus={(e) => {
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
                  }}
                />
                <button
                  type="button"
                  className={`poster-topic-search-btn${topic.search ? " poster-topic-search-btn--active" : ""}`}
                  disabled={f}
                  onClick={() => toggleTopicSearch(idx)}
                  title={topic.search ? "Поиск Яндекс включён — при генерации поста выполнится поиск актуальных данных" : "Включить поиск Яндекс для этой темы"}
                >
                  🔍
                </button>
                {cfg.poster_topic_list.length > 1 && !f && (
                  <button type="button" className="poster-topic-remove" onClick={() => removeTopic(idx)}
                    title="Удалить тему" aria-label="Удалить">×</button>
                )}
              </div>
            ))}
          </div>
          {!f && cfg.poster_topic_list.length < 20 && (
            <button type="button" className="poster-add-slot" onClick={addTopic} style={{ marginTop: 6 }}>
              + Добавить тему
            </button>
          )}
          {cfg.poster_topic_mode === "priority" && (
            <span className="poster-field__hint">⬆️ Темы выше в списке — публикуются чаще</span>
          )}
        </div>

        {/* Topic rotation mode */}
        <div className="poster-field">
          <label className="poster-field__label">Порядок публикации тем</label>
          <select
            className="poster-field__select"
            value={cfg.poster_topic_mode}
            disabled={f}
            onChange={(e) => patch("poster_topic_mode", e.target.value)}
          >
            <option value="no_repeat">Случайный без повторов</option>
            <option value="random">Случайный</option>
            <option value="sequential">По очереди (1→2→3→...)</option>
            <option value="priority">Приоритетный (первые чаще)</option>
          </select>
          <span className="poster-field__hint">
            {cfg.poster_topic_mode === "no_repeat" && "Выбирает случайно, но не повторяет тему дважды подряд"}
            {cfg.poster_topic_mode === "random" && "Выбирает любую тему полностью случайно"}
            {cfg.poster_topic_mode === "sequential" && "Строго по порядку сверху вниз, затем начинает снова"}
            {cfg.poster_topic_mode === "priority" && "Тема 1 — самая частая, последняя — наименее частая"}
          </span>
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

        {/* ── Качество контента ───────────────────────────────────────── */}
        <ChipsField
          label="Формат поста"
          value={cfg.poster_format === "auto" ? "" : cfg.poster_format}
          chips={cfg.poster_format_chips}
          disabled={f}
          hint="Можно выбрать несколько форматов или ввести свой. Добавьте и удалите варианты."
          onChange={(v) => patch("poster_format", v || "auto")}
          onChipsChange={(chips) => patch("poster_format_chips", chips)}
        />

        <ChipsField
          label="Стиль первой строки (хук)"
          value={cfg.poster_hook === "auto" ? "" : cfg.poster_hook}
          chips={cfg.poster_hook_chips}
          disabled={f}
          hint="Первая строка — главный крючок для читателя."
          onChange={(v) => patch("poster_hook", v || "auto")}
          onChipsChange={(chips) => patch("poster_hook_chips", chips)}
        />

        <ChipsField
          label="Целевая аудитория"
          value={cfg.poster_audience}
          chips={cfg.poster_audience_chips}
          disabled={f}
          hint="LLM подстраивает лексику и примеры под описание аудитории."
          onChange={(v) => patch("poster_audience", v)}
          onChipsChange={(chips) => patch("poster_audience_chips", chips)}
        />

        <ChipsField
          label="Тип призыва к действию (CTA)"
          value={cfg.poster_cta_type === "none" ? "" : cfg.poster_cta_type}
          chips={cfg.poster_cta_chips}
          disabled={f}
          hint="Пусто — без CTA. Можно выбрать несколько или написать свой."
          onChange={(v) => patch("poster_cta_type", v || "none")}
          onChipsChange={(chips) => patch("poster_cta_chips", chips)}
        />

        {/* Approval + Reflection */}
        <div className="poster-field-row">
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input
              type="checkbox"
              checked={cfg.poster_approval}
              disabled={f}
              onChange={(e) => {
                if (!e.target.checked) {
                  // Ask for confirmation before disabling approval
                  setApprovalConfirmModal(true);
                } else {
                  patch("poster_approval", true);
                }
              }}
            />
            <span>Согласование перед публикацией</span>
          </label>
          <label className={`poster-toggle${f ? " poster-toggle--disabled" : ""}`}>
            <input type="checkbox" checked={cfg.poster_reflection} disabled={f} onChange={(e) => patch("poster_reflection", e.target.checked)} />
            <span>Проверка качества поста {isFree ? "(Lite ИИ, + 1 запрос)" : "(+ 1 запрос)"}</span>
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
            {saving ? "Сохраняем…"
              : verifying && verifyStep === "channel" ? "Проверяем канал…"
              : verifying && verifyStep === "admin" ? "Проверяем права…"
              : verifying ? "Проверяем…"
              : "Сохранить настройки"}
          </button>
        </div>
      </div>

      {/* Status messages */}
      {(saving || verifying) && (
        <div className="poster-status poster-status--checking">
          <span className="poster-status__spinner" />
          {verifying && verifyStep === "channel" && "Проверяем доступ к каналу…"}
          {verifying && verifyStep === "admin" && "Проверяем права администратора…"}
          {verifying && !verifyStep && "Проверяем канал…"}
          {saving && "Сохраняем настройки…"}
        </div>
      )}
      {!saving && !verifying && showActiveUI && (
        <div className="poster-status poster-status--active">
          ✅ Агент активирован. {activationHint}
        </div>
      )}
      {/* Free tier notice — shown whenever the toggle is on */}
      {enabled && isFree && (
        <div className="poster-free-notice">
          ℹ️ Вы используете бесплатный тариф. При генерации текста используется лёгкая версия ИИ, а также некоторые функции ограничены.
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

              {/* Image management block */}
              {draftAction !== "editing" && (
                <div className="poster-draft__media">
                  {/* Image previews grid */}
                  {draftImages.length > 0 && (
                    <div className="poster-draft__images-grid">
                      {draftImages.map((img, idx) => (
                        <div key={idx} className="poster-draft__img-thumb">
                          <img src={img.url} alt={`Фото ${idx + 1}`} />
                          <button
                            type="button"
                            className="poster-draft__img-remove"
                            onClick={() => handleRemoveImage(idx)}
                            title="Удалить"
                            aria-label="Удалить фото"
                          >×</button>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Image action buttons */}
                  <div className="poster-draft__media-actions">
                    <button
                      type="button"
                      className="poster-draft__media-btn"
                      disabled={imageRegenLoading || imageUploadLoading || cfg.poster_media !== "ai"}
                      onClick={cfg.poster_media === "ai" ? handleRegenImage : () => setDraftError("Для генерации ИИ-картинки выберите «ИИ-изображение» в настройках агента выше.")}
                      title={cfg.poster_media === "ai" ? "Сгенерировать новое ИИ-изображение" : "Выберите «ИИ-изображение» в настройках"}
                      style={cfg.poster_media !== "ai" ? { opacity: 0.4, cursor: "not-allowed" } : undefined}
                    >
                      {imageRegenLoading ? <span className="poster-status__spinner" /> : "🤖"} ИИ-картинка
                    </button>
                    {draftImages.length < 4 && (
                      <button
                        type="button"
                        className="poster-draft__media-btn"
                        disabled={imageRegenLoading || imageUploadLoading}
                        onClick={() => imageInputRef.current?.click()}
                        title="Загрузить фото (до 4)"
                      >
                        {imageUploadLoading ? <span className="poster-status__spinner" /> : "📎"} Загрузить ({draftImages.length}/4)
                      </button>
                    )}
                    {draftImages.length > 0 && (
                      <button
                        type="button"
                        className="poster-draft__media-btn poster-draft__media-btn--danger"
                        disabled={imageRegenLoading || imageUploadLoading}
                        onClick={async () => {
                          // Remove all images: sync each fileId with backend
                          if (draft) {
                            const toRemove = draftImages.filter(img => img.fileId);
                            for (const img of toRemove) {
                              await callDraftAction({ action: "remove_image", post_id: draft.postId, file_id: img.fileId }).catch(() => null);
                            }
                          }
                          setDraftImages([]);
                        }}
                        title="Убрать все фото"
                      >
                        ✕ Без фото
                      </button>
                    )}
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      hidden
                      onChange={handleUploadImages}
                    />
                  </div>
                  {/* Show image/upload errors inline (visible in non-edit mode) */}
                  {draftError && draftAction !== "error" && (
                    <div className="poster-draft__media-error">⚠️ {draftError}</div>
                  )}
                </div>
              )}

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
                    disabled={draftAction === "actioning" || imageRegenLoading || imageUploadLoading}
                    onClick={() => handleDraftAction("approve")}
                  >
                    {draftAction === "actioning" ? <span className="poster-status__spinner" /> : "✅"} Опубликовать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--regen"
                    disabled={draftAction === "actioning" || imageRegenLoading || imageUploadLoading}
                    onClick={() => handleDraftAction("regen")}
                    title={imageRegenLoading ? "Дождитесь загрузки изображения" : undefined}
                  >
                    🔄 Перегенерировать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--edit"
                    disabled={draftAction === "actioning" || imageRegenLoading || imageUploadLoading}
                    onClick={handleStartEdit}
                  >
                    ✏️ Редактировать
                  </button>
                  <button
                    type="button"
                    className="poster-draft__btn poster-draft__btn--reject"
                    disabled={draftAction === "actioning" || imageRegenLoading || imageUploadLoading}
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

      {/* Post history */}
      {showActiveUI && (
        <div className="poster-history">
          <div className="poster-history__header">
            <span className="poster-history__title">История постов</span>
            <div className="poster-history__header-actions">
              {selectedIds.size > 0 && (
                <button type="button" className="poster-history__action-btn poster-history__action-btn--danger"
                  onClick={deleteSelected}>Удалить {selectedIds.size}</button>
              )}
              {(historyPage?.total ?? 0) > 0 && (
                <button type="button" className="poster-history__action-btn poster-history__action-btn--danger"
                  onClick={clearAllHistory}>Очистить всё</button>
              )}
              <button type="button" className="poster-history__refresh"
                onClick={() => void loadHistory()}>{historyLoading ? "⟳" : "↺"}</button>
            </div>
          </div>
          <div className="poster-history__search-wrap">
            <input className="poster-history__search" type="search" placeholder="Поиск по теме…"
              value={historySearch} onChange={(e) => handleHistorySearch(e.target.value)} />
          </div>
          {!historyPage || historyPage.items.length === 0 ? (
            <div className="poster-history__empty">{historySearch ? "Ничего не найдено" : "Постов ещё нет"}</div>
          ) : (
            <>
              <div className="poster-history__list">
                {historyPage.items.map((item) => {
                  const expanded = expandedIds.has(item.id);
                  const selected = selectedIds.has(item.id);
                  return (
                    <div key={item.id} className={`poster-history__item${selected ? " poster-history__item--selected" : ""}`}>
                      <div className="poster-history__item-left">
                        <input type="checkbox" checked={selected} onChange={() => toggleSelect(item.id)} className="poster-history__checkbox" />
                        <span className="poster-history__badge">
                          {item.status === "published" ? "✅" : item.status === "rejected" ? "❌" : "📝"}
                        </span>
                      </div>
                      <div className="poster-history__item-body">
                        <div className="poster-history__item-row">
                          <button type="button" className="poster-history__topic" onClick={() => toggleExpand(item.id)}>
                            {item.topic}<span className="poster-history__expand-icon">{expanded ? " ▲" : " ▼"}</span>
                          </button>
                          <span className="poster-history__date">{
                            item.at ? new Date(item.at).toLocaleString("ru-RU", {
                              day: "2-digit", month: "2-digit", year: "numeric",
                              hour: "2-digit", minute: "2-digit",
                            }) : ""
                          }</span>
                        </div>
                        {expanded && item.text && (
                          <div className="poster-history__text">{item.text}</div>
                        )}
                        {expanded && (
                          <div className="poster-history__item-actions">
                            {item.text && (
                              <button type="button" className="poster-history__act-btn" onClick={() => useAsBase(item)}>
                                ✏️ Использовать как основу
                              </button>
                            )}
                            <button type="button" className="poster-history__act-btn poster-history__act-btn--danger"
                              onClick={() => deleteHistoryItem(item.id)}>🗑 Удалить</button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
              {historyPage.pages > 1 && (
                <div className="poster-history__pagination">
                  <button type="button" className="poster-history__page-btn"
                    disabled={historyCurrentPage <= 1} onClick={() => handleHistoryPage(historyCurrentPage - 1)}>←</button>
                  <span className="poster-history__page-info">
                    {historyCurrentPage} / {historyPage.pages}
                    <span className="poster-history__page-total"> ({historyPage.total})</span>
                  </span>
                  <button type="button" className="poster-history__page-btn"
                    disabled={historyCurrentPage >= historyPage.pages} onClick={() => handleHistoryPage(historyCurrentPage + 1)}>→</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Image generation limit modal (Free users) */}
      {imageLimitModal && (
        <ProUpgradeModal
          open={imageLimitModal}
          title="Лимит генерации изображений исчерпан"
          description="На бесплатном тарифе количество ИИ-картинок ограничено. Перейдите на Pro для неограниченной генерации, или загрузите своё фото."
          onClose={() => setImageLimitModal(false)}
        />
      )}

      {/* Approval confirmation modal */}
      {approvalConfirmModal && (
        <div
          className="app-modal-overlay poster-confirm-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setApprovalConfirmModal(false); }}
        >
          <div className="app-modal feedback-modal poster-confirm-modal" role="dialog" aria-modal="true">
            <h3 className="feedback-modal-title">Отключить согласование?</h3>
            <p className="feedback-modal-hint">
              Посты будут публиковаться в канал автоматически, без вашего подтверждения каждого поста.
            </p>
            <div className="feedback-modal-actions poster-confirm-modal__actions">
              <button
                type="button"
                className="btn-primary danger"
                onClick={() => { patch("poster_approval", false); setApprovalConfirmModal(false); }}
              >
                Да, публиковать автоматически
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setApprovalConfirmModal(false)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
