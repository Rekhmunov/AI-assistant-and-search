import { useState, useEffect, useCallback } from "react";
import { useAuthStore } from "../store/authStore";
import { useTouchThread } from "../hooks/useTouchThread";

const API_BASE = import.meta.env.VITE_API_URL || "";

type RecordItem = {
  _id: string;
  category: string;
  amount: number;
  note?: string;
  at: string;
  author?: string;
};

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit", month: "2-digit", year: "2-digit",
    });
  } catch { return iso.slice(0, 10); }
}

function formatAmount(n: number): string {
  return n.toLocaleString("ru-RU");
}

export function SecretarySettingsPanel({ threadId, initialConfig }: Props) {
  const token = useAuthStore((s) => s.token);
  const touchThread = useTouchThread(threadId, token);

  // ── Config state ─────────────────────────────────────────────────────────
  const [enabled, setEnabled]             = useState(true);
  const [groupInput, setGroupInput]       = useState("");
  const [categories, setCategories]       = useState("");
  const [catDirty, setCatDirty]           = useState(false);
  const [compiledOk, setCompiledOk]       = useState<boolean | null>(null);

  const CAT_LIMIT = 4000;

  // Group status
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [verifyResult, setVerifyResult]   = useState<{
    ok: boolean; chat_name?: string; error?: string; group_id?: number;
  } | null>(null);

  // Save status
  const [saving, setSaving]     = useState(false);
  const [saveOk, setSaveOk]     = useState(false);
  const [saveError, setSaveError] = useState("");

  // Records
  const [records, setRecords]           = useState<RecordItem[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recLoading, setRecLoading]     = useState(false);
  const [clearConfirm, setClearConfirm] = useState(false);


  // ── Init from backend config ──────────────────────────────────────────────
  useEffect(() => {
    if (!initialConfig) return;
    const c = initialConfig as Record<string, unknown>;
    const raw = String(c.support_instructions || "");
    const cats = raw.replace(/^категории затрат:\s*/i, "").split(/;|\n/).map(s => s.trim()).filter(Boolean);
    setCategories(cats.join("\n"));
    const chatId = c.max_chat_id ? String(c.max_chat_id) : "";
    setGroupInput(chatId);
    if (chatId) setVerifyResult({ ok: true, chat_name: chatId });
    setEnabled(c.secretary_enabled !== false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const headers = useCallback((): HeadersInit => ({
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }), [token]);

  // ── Load records ──────────────────────────────────────────────────────────
  const loadRecords = useCallback(async () => {
    setRecLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/agent/threads/${threadId}/records?limit=50`,
        { headers: headers() }
      );
      if (res.ok) {
        const d = await res.json();
        setRecords(d.records || []);
        setRecordsTotal(d.total || 0);
      }
    } catch { /* silent */ } finally { setRecLoading(false); }
  }, [threadId, headers]);

  useEffect(() => { void loadRecords(); }, [loadRecords]);

  // ── Toggle enabled ────────────────────────────────────────────────────────
  async function handleToggle(val: boolean) {
    setEnabled(val);
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
      method: "PATCH", headers: headers(),
      body: JSON.stringify({ secretary_enabled: val }),
    }).catch(() => null);
  }

  // ── Save categories ───────────────────────────────────────────────────────
  async function saveCategories() {
    setSaving(true); setSaveOk(false); setSaveError(""); setCompiledOk(null);
    try {
      const cats = categories.trim();
      const instructions = cats.toLowerCase().startsWith("категории затрат:")
        ? cats
        : `Категории затрат: ${cats.replace(/\n+/g, "; ").replace(/;+/g, ";").replace(/;\s*;/g, ";")}`;
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH", headers: headers(),
        body: JSON.stringify({ support_instructions: instructions }),
      });
      if (res.ok) {
        const d = await res.json();
        setSaveOk(true);
        setCatDirty(false);
        if (typeof d.compiled_rules === "boolean") setCompiledOk(d.compiled_rules);
        setTimeout(() => { setSaveOk(false); setCompiledOk(null); }, 5000);
      } else {
        setSaveError("Ошибка сохранения");
      }
    } catch { setSaveError("Ошибка соединения"); }
    finally { setSaving(false); }
  }

  // ── Verify group ──────────────────────────────────────────────────────────
  async function verifyGroup() {
    if (!groupInput.trim()) return;
    setVerifyLoading(true); setVerifyResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/verify-group`, {
        method: "POST", headers: headers(),
        body: JSON.stringify({ group_id: groupInput.trim() }),
      });
      const d = await res.json();
      setVerifyResult(d);
      if (d.ok) setGroupInput(String(d.group_id || groupInput.trim()));
    } catch { setVerifyResult({ ok: false, error: "Ошибка соединения" }); }
    finally { setVerifyLoading(false); }
  }

  // ── Delete record ─────────────────────────────────────────────────────────
  async function deleteRecord(id: string) {
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/records/${id}`, {
      method: "DELETE", headers: headers(),
    }).catch(() => null);
    setRecords(r => r.filter(x => x._id !== id));
    setRecordsTotal(t => Math.max(0, t - 1));
  }

  // ── Clear all records ─────────────────────────────────────────────────────
  async function clearAll() {
    await fetch(`${API_BASE}/api/agent/threads/${threadId}/records/clear`, {
      method: "POST", headers: headers(),
    }).catch(() => null);
    setRecords([]); setRecordsTotal(0); setClearConfirm(false);
  }

  const f = !enabled;
  const groupOk = verifyResult?.ok;
  const groupName = verifyResult?.chat_name || "";

  return (
    <div className={`poster-settings${f ? " poster-settings--disabled" : ""}`}>

      {/* ── Header + toggle ─────────────────────────────────────────────── */}
      <div className="poster-settings__header">
        <span className="poster-settings__title">Учёт затрат</span>
        <label className="poster-settings__toggle">
          <input type="checkbox" checked={enabled} onChange={e => handleToggle(e.target.checked)} />
          <span className="poster-settings__toggle-track">
            <span className="poster-settings__toggle-thumb" />
          </span>
          <span className="poster-settings__toggle-label">
            {enabled ? "Включён" : "Выключен"}
          </span>
        </label>
      </div>

      <div className="poster-settings__body">

        {/* ── Группа MAX ─────────────────────────────────────────────────── */}
        <div className="poster-field">
          <label className="poster-field__label">
            Группа MAX <span className="poster-field__required">*</span>
          </label>
          <input
            className={`poster-field__input${!groupOk && enabled ? " poster-field__input--error" : ""}`}
            type="text"
            placeholder="@mygroup или -123456789"
            value={groupInput}
            disabled={f}
            onChange={e => { void touchThread(); setGroupInput(e.target.value); }}
            onKeyDown={e => { if (e.key === "Enter") void verifyGroup(); }}
          />
          <span className="poster-field__hint">
            Ссылка или ID группы, куда добавлен бот
          </span>
          {groupOk ? (
            <span style={{ fontSize: "0.82rem", color: "#276749" }}>
              ✅ Подключено{groupName ? `: ${groupName}` : ""}
            </span>
          ) : verifyResult && !verifyResult.ok ? (
            <span className="poster-settings__error">
              {verifyResult.error || "Не удалось подключить группу"}
            </span>
          ) : null}
          <div style={{ marginTop: 6 }}>
            <button
              type="button"
              className="poster-settings__save"
              disabled={f || verifyLoading || !groupInput.trim()}
              onClick={verifyGroup}
            >
              {verifyLoading ? "Проверка…" : groupOk ? "Переподключить" : "Подключить группу"}
            </button>
          </div>
        </div>

        {/* ── Категории затрат ────────────────────────────────────────────── */}
        <div className="poster-field">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
            <label className="poster-field__label" style={{ marginBottom: 0 }}>
              Категории затрат <span className="poster-field__required">*</span>
            </label>
            <span style={{
              fontSize: "0.75rem",
              color: categories.length > CAT_LIMIT * 0.9 ? (categories.length >= CAT_LIMIT ? "#e53e3e" : "#d97706") : "var(--text-secondary, #888)",
              flexShrink: 0,
            }}>
              {categories.length} / {CAT_LIMIT}
            </span>
          </div>
          <textarea
            className="poster-field__textarea"
            rows={6}
            placeholder={"Аренда\nЗарплата\nТранспорт\nМатериалы\nРеклама"}
            value={categories}
            disabled={f}
            maxLength={CAT_LIMIT}
            onChange={e => { void touchThread(); setCategories(e.target.value); setCatDirty(true); setSaveError(""); setCompiledOk(null); }}
          />
          <span className="poster-field__hint">
            Каждая категория с новой строки или через «;»
          </span>
          {saveError && <span className="poster-settings__error">{saveError}</span>}
        </div>

        {/* ── Footer: Save ─────────────────────────────────────────────────── */}
        <div className="poster-settings__footer">
          {saving && (
            <span style={{ fontSize: "0.82rem", color: "var(--text-secondary, #888)", flex: 1 }}>
              Сохранение и компиляция правил…
            </span>
          )}
          {!saving && saveOk && (
            <span style={{ fontSize: "0.85rem", color: "#276749", flex: 1 }}>
              {compiledOk === true
                ? "✅ Сохранено, правила обновлены"
                : compiledOk === false
                ? "✅ Сохранено (правила не скомпилированы — подключите группу)"
                : "✅ Сохранено"}
            </span>
          )}
          <button
            type="button"
            className="poster-settings__save"
            disabled={f || saving || !catDirty}
            onClick={saveCategories}
          >
            {saving ? "Сохранение…" : "Сохранить"}
          </button>
        </div>

        {/* ── Записи о затратах ────────────────────────────────────────────── */}
        <div className="poster-field">
          <label className="poster-field__label">
            Записи о затратах
            {recordsTotal > 0 && (
              <span style={{
                marginLeft: 8, padding: "1px 8px", borderRadius: 20,
                background: "var(--accent,#20808d)", color: "#fff",
                fontSize: "0.72rem", fontWeight: 700,
              }}>{recordsTotal}</span>
            )}
          </label>

          {recLoading ? (
            <span className="poster-field__hint">Загрузка…</span>
          ) : records.length === 0 ? (
            <span className="poster-field__hint">Записей пока нет</span>
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
                {records.map(r => (
                  <div key={r._id} className="secretary-records-table__row">
                    <span className="secretary-records-table__date">{formatDate(r.at)}</span>
                    <span className="secretary-records-table__category">{r.category}</span>
                    <span className="secretary-records-table__amount">{formatAmount(r.amount)}</span>
                    <span className="secretary-records-table__note">{r.note || "—"}</span>
                    <button
                      className="secretary-records-table__del"
                      onClick={() => void deleteRecord(r._id)}
                      title="Удалить"
                    >✕</button>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: 8 }}>
                {!clearConfirm ? (
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: "0.82rem", color: "#e53e3e", border: "1px solid #e53e3e" }}
                    onClick={() => setClearConfirm(true)}
                  >
                    Очистить все записи
                  </button>
                ) : (
                  <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span className="poster-field__hint">
                      Удалить все {recordsTotal} записей?
                    </span>
                    <button
                      type="button"
                      className="poster-settings__save"
                      style={{ background: "#e53e3e" }}
                      onClick={clearAll}
                    >Да, удалить</button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setClearConfirm(false)}
                    >Отмена</button>
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {/* ── Отчёты ──────────────────────────────────────────────────────── */}
        <div className="poster-field">
          <label className="poster-field__label">Отчёты</label>
          <span className="poster-field__hint">
            Для получения отчёта напишите <strong>«отчёт»</strong> в подключённой группе —
            бот спросит период и пришлёт Excel-файл с диаграммой прямо в чат.
          </span>
        </div>

      </div>
    </div>
  );
}
