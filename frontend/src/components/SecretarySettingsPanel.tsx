import { useState, useEffect, useCallback } from "react";
import { useAuthStore } from "../store/authStore";

const API_BASE = import.meta.env.VITE_API_URL || "";

type RecordItem = {
  _id: string;
  category: string;
  amount: number;
  note?: string;
  at: string;
  author?: string;
};

type SecretaryConfig = {
  support_instructions: string;
  max_chat_id: string;
  secretary_enabled: boolean;
  bot_is_group_admin?: boolean;
  agent_status?: string;
};

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatAmount(n: number): string {
  return n.toLocaleString("ru-RU");
}

export function SecretarySettingsPanel({ threadId, initialConfig }: Props) {
  const token = useAuthStore((s) => s.token);

  const [config, setConfig] = useState<SecretaryConfig>({
    support_instructions: "",
    max_chat_id: "",
    secretary_enabled: true,
    bot_is_group_admin: undefined,
    agent_status: "",
  });
  const [initDone, setInitDone] = useState(false);

  // Group verification state
  const [groupInput, setGroupInput] = useState("");
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    ok: boolean; chat_name?: string; error?: string; group_id?: number;
  } | null>(null);

  // Categories save state
  const [categoriesDirty, setCategoriesDirty] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveResult, setSaveResult] = useState<string | null>(null);

  // Records state
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [clearConfirm, setClearConfirm] = useState(false);

  // Init from backend config
  useEffect(() => {
    if (initDone || !initialConfig) return;
    setInitDone(true);
    const c = initialConfig as Record<string, unknown>;
    const instructions = String(c.support_instructions || "");
    const chatId = c.max_chat_id ? String(c.max_chat_id) : "";
    setConfig({
      support_instructions: instructions,
      max_chat_id: chatId,
      secretary_enabled: c.secretary_enabled !== false,
      bot_is_group_admin: c.bot_is_group_admin as boolean | undefined,
      agent_status: String(c.agent_status || ""),
    });
    setGroupInput(chatId);
    if (chatId) {
      setVerifyResult({ ok: true, chat_name: chatId });
    }
  }, [initialConfig, initDone]);

  // Reset when navigating to another thread
  useEffect(() => {
    setInitDone(false);
    setVerifyResult(null);
    setCategoriesDirty(false);
    setSaveResult(null);
  }, [threadId]);

  const headers = useCallback((): HeadersInit => ({
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }), [token]);

  // Load records
  const loadRecords = useCallback(async () => {
    setRecordsLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/records?limit=50`,
        { headers: headers() }
      );
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
        setRecordsTotal(data.total || 0);
      }
    } catch {
      // non-fatal
    } finally {
      setRecordsLoading(false);
    }
  }, [threadId, headers]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  // Toggle enabled
  async function toggleEnabled(val: boolean) {
    setConfig((c) => ({ ...c, secretary_enabled: val }));
    try {
      await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ secretary_enabled: val }),
      });
    } catch {
      // non-fatal
    }
  }

  // Save categories
  async function saveCategories() {
    setSaveLoading(true);
    setSaveResult(null);
    try {
      const cats = config.support_instructions.trim();
      // Format as the LLM onboarding would: "Категории затрат: A; B; C"
      let instructions = cats;
      if (cats && !cats.toLowerCase().startsWith("категории затрат:")) {
        instructions = `Категории затрат: ${cats.replace(/\n+/g, "; ").replace(/;+/g, ";").replace(/;\s*;/g, ";")}`;
      }
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        headers: headers(),
        body: JSON.stringify({ support_instructions: instructions }),
      });
      if (res.ok) {
        setConfig((c) => ({ ...c, support_instructions: instructions }));
        setSaveResult("ok");
        setCategoriesDirty(false);
      } else {
        setSaveResult("error");
      }
    } catch {
      setSaveResult("error");
    } finally {
      setSaveLoading(false);
      setTimeout(() => setSaveResult(null), 3000);
    }
  }

  // Verify group
  async function verifyGroup() {
    const raw = groupInput.trim();
    if (!raw) return;
    setVerifyLoading(true);
    setVerifyResult(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/verify-group`,
        {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ group_id: raw }),
        }
      );
      const data = await res.json();
      setVerifyResult(data);
      if (data.ok) {
        setConfig((c) => ({ ...c, max_chat_id: String(data.group_id || raw) }));
      }
    } catch (e) {
      setVerifyResult({ ok: false, error: "Ошибка соединения" });
    } finally {
      setVerifyLoading(false);
    }
  }

  // Delete record
  async function deleteRecord(id: string) {
    try {
      await fetch(`${API_BASE}/api/agent/threads/${threadId}/records/${id}`, {
        method: "DELETE",
        headers: headers(),
      });
      setRecords((r) => r.filter((x) => x._id !== id));
      setRecordsTotal((t) => Math.max(0, t - 1));
    } catch {
      // non-fatal
    }
  }

  // Clear all records
  async function clearAllRecords() {
    try {
      await fetch(`${API_BASE}/api/agent/threads/${threadId}/records/clear`, {
        method: "POST",
        headers: headers(),
      });
      setRecords([]);
      setRecordsTotal(0);
      setClearConfirm(false);
    } catch {
      setClearConfirm(false);
    }
  }

  const isActive = config.agent_status === "active";
  const groupConnected = verifyResult?.ok || Boolean(config.max_chat_id);
  const groupName = verifyResult?.chat_name || config.max_chat_id || "";

  // Parse categories for display
  const categoriesRaw = config.support_instructions || "";
  const categoriesDisplay = categoriesRaw
    .replace(/^категории затрат:\s*/i, "")
    .split(/;|\n/)
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div className="poster-settings-wrap">
      {/* ── Заголовок + тогл ── */}
      <div className="poster-header">
        <div className="poster-header__left">
          <span className="poster-header__title">Учёт затрат</span>
          <span
            className={`poster-header__status ${isActive ? "poster-header__status--active" : ""}`}
          >
            {isActive ? "Активен" : "Настройка"}
          </span>
        </div>
        <label className="poster-toggle">
          <input
            type="checkbox"
            checked={config.secretary_enabled}
            onChange={(e) => toggleEnabled(e.target.checked)}
          />
          <span className="poster-toggle__slider" />
        </label>
      </div>

      {/* ── Блок: Группа ── */}
      <div className="poster-section">
        <div className="poster-section__title">Группа MAX</div>
        {groupConnected ? (
          <div className="poster-channel-status poster-channel-status--ok">
            ✅ Группа подключена{groupName ? `: ${groupName}` : ""}
          </div>
        ) : (
          <div className="poster-channel-status poster-channel-status--warn">
            ⚠️ Группа не подключена
          </div>
        )}
        <div className="poster-channel-row">
          <input
            className="poster-input"
            placeholder="Ссылка, @username или ID группы"
            value={groupInput}
            onChange={(e) => setGroupInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") verifyGroup(); }}
          />
          <button
            className="poster-btn poster-btn--primary"
            onClick={verifyGroup}
            disabled={verifyLoading || !groupInput.trim()}
          >
            {verifyLoading ? "Проверка…" : groupConnected ? "Переподключить" : "Подключить"}
          </button>
        </div>
        {verifyResult && !verifyResult.ok && (
          <div className="poster-error">{verifyResult.error || "Не удалось подключить группу"}</div>
        )}
        <div className="poster-hint">
          Бот должен быть добавлен в группу. Для чтения всех сообщений — назначьте его администратором.
        </div>
      </div>

      {/* ── Блок: Категории ── */}
      <div className="poster-section">
        <div className="poster-section__title">Категории затрат</div>
        <div className="poster-hint">
          Каждая категория с новой строки или через «;»
        </div>
        <textarea
          className="poster-textarea"
          rows={6}
          placeholder={"Аренда\nЗарплата\nТранспорт\nМатериалы"}
          value={categoriesDisplay.join("\n")}
          onChange={(e) => {
            setConfig((c) => ({ ...c, support_instructions: e.target.value }));
            setCategoriesDirty(true);
            setSaveResult(null);
          }}
        />
        <div className="poster-actions-row">
          <button
            className="poster-btn poster-btn--primary"
            onClick={saveCategories}
            disabled={saveLoading || !categoriesDirty}
          >
            {saveLoading ? "Сохранение…" : "Сохранить категории"}
          </button>
          {saveResult === "ok" && (
            <span className="poster-save-ok">✅ Сохранено</span>
          )}
          {saveResult === "error" && (
            <span className="poster-error">Ошибка сохранения</span>
          )}
        </div>
      </div>

      {/* ── Блок: Записи ── */}
      <div className="poster-section">
        <div className="poster-section__title">
          Записи о затратах
          {recordsTotal > 0 && (
            <span className="poster-badge">{recordsTotal}</span>
          )}
        </div>

        {recordsLoading ? (
          <div className="poster-hint">Загрузка…</div>
        ) : records.length === 0 ? (
          <div className="poster-hint">Записей пока нет</div>
        ) : (
          <>
            <div className="secretary-records-table">
              <div className="secretary-records-table__header">
                <span>Дата</span>
                <span>Категория</span>
                <span>Сумма</span>
                <span>Примечание</span>
                <span />
              </div>
              {records.map((r) => (
                <div key={r._id} className="secretary-records-table__row">
                  <span className="secretary-records-table__date">
                    {formatDate(r.at)}
                  </span>
                  <span className="secretary-records-table__category">
                    {r.category}
                  </span>
                  <span className="secretary-records-table__amount">
                    {formatAmount(r.amount)}
                  </span>
                  <span className="secretary-records-table__note">
                    {r.note || "—"}
                  </span>
                  <button
                    className="secretary-records-table__del"
                    onClick={() => deleteRecord(r._id)}
                    title="Удалить запись"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <div className="poster-actions-row" style={{ marginTop: 8 }}>
              {!clearConfirm ? (
                <button
                  className="poster-btn poster-btn--danger"
                  onClick={() => setClearConfirm(true)}
                >
                  Очистить все записи
                </button>
              ) : (
                <>
                  <span className="poster-hint">Удалить все {recordsTotal} записей?</span>
                  <button className="poster-btn poster-btn--danger" onClick={clearAllRecords}>
                    Да, удалить
                  </button>
                  <button className="poster-btn" onClick={() => setClearConfirm(false)}>
                    Отмена
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Блок: Отчёты ── */}
      <div className="poster-section">
        <div className="poster-section__title">Отчёты</div>
        <div className="poster-hint">
          Для получения отчёта напишите <strong>«отчёт»</strong> в подключённой группе —
          бот спросит период и пришлёт Excel-файл прямо в чат.
        </div>
      </div>
    </div>
  );
}
