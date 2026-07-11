import { useState, useEffect, useRef } from "react";
import { Pencil, Paperclip, ChevronDown, ChevronUp } from "lucide-react";
import { useAuthStore } from "../store/authStore";
import { useTouchThread } from "../hooks/useTouchThread";

const API_BASE = import.meta.env.VITE_API_URL || "";

const PLACEHOLDER = `Примеры инструкций:

Ты — опытный копирайтер. Пиши продающие тексты в дружелюбном тоне. Используй короткие абзацы и заголовки. Всегда предлагай несколько вариантов.

Ты — юрист, специализирующийся на российском праве. Отвечай точно, ссылайся на статьи законов, предупреждай о рисках.

Ты — ментор по продуктовому менеджменту. Задавай уточняющие вопросы, помогай структурировать мысли.`;

const PREVIEW_LEN = 120;

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
};

export function ExpertSettingsPanel({ threadId, initialConfig }: Props) {
  const token = useAuthStore((s) => s.token);
  const touchThread = useTouchThread(threadId, token);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const saved_instruction = String(initialConfig?.expert_instruction ?? "");
  const [instruction, setInstruction] = useState(saved_instruction);
  const [useHistory, setUseHistory] = useState(
    initialConfig?.expert_use_history !== false // по умолчанию true
  );
  const [useSearch, setUseSearch] = useState(
    Boolean(initialConfig?.expert_use_search) // по умолчанию false
  );
  const [editing, setEditing] = useState(!saved_instruction);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [error, setError] = useState("");
  const [fileLoading, setFileLoading] = useState(false);

  useEffect(() => {
    const val = String(initialConfig?.expert_instruction ?? "");
    setInstruction(val);
    setUseHistory(initialConfig?.expert_use_history !== false);
    setUseSearch(Boolean(initialConfig?.expert_use_search));
    if (!val) setEditing(true);
  }, [initialConfig?.expert_instruction, initialConfig?.expert_use_history, initialConfig?.expert_use_search]);

  const authHeaders = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({
          expert_instruction: instruction,
          expert_use_history: useHistory,
          expert_use_search: useSearch,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSavedOk(true);
      setEditing(false);
      setTimeout(() => setSavedOk(false), 2000);
    } catch (e: any) {
      setError(e.message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setFileLoading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/files/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const text = data.extracted_text || data.text || "";
      if (!text.trim()) {
        setError("Не удалось извлечь текст из файла.");
        return;
      }
      const trimmed = text.slice(0, 6000);
      void touchThread();
      setInstruction((prev) =>
        prev
          ? `${prev}\n\n--- Содержимое файла «${file.name}» ---\n${trimmed}`
          : `--- Содержимое файла «${file.name}» ---\n${trimmed}`
      );
    } catch (e: any) {
      setError(e.message || "Ошибка загрузки файла");
    } finally {
      setFileLoading(false);
    }
  };

  const preview = instruction.length > PREVIEW_LEN
    ? instruction.slice(0, PREVIEW_LEN) + "…"
    : instruction;

  return (
    <div className="expert-settings-panel">
      <div className="expert-settings-header">
        <div className="expert-settings-header-row">
          <h3 className="expert-settings-title">Инструкция</h3>
          {!editing && instruction && (
            <button
              type="button"
              className="expert-edit-btn"
              onClick={() => setEditing(true)}
              title="Редактировать инструкцию"
            >
              <Pencil width={14} height={14} strokeWidth={2} />
              Редактировать
            </button>
          )}
        </div>
        {!editing && instruction ? (
          <p className="expert-settings-preview">{preview}</p>
        ) : (
          <p className="expert-settings-sub">
            Задайте роль, стиль ответов или правила — агент будет следовать им в каждом сообщении.
          </p>
        )}
      </div>

      {editing && (
        <>
          <div className="expert-settings-body">
            <textarea
              className="expert-settings-textarea"
              value={instruction}
              onChange={(e) => {
                void touchThread();
                setInstruction(e.target.value);
              }}
              placeholder={PLACEHOLDER}
              rows={10}
              maxLength={8000}
              autoFocus
            />
            <label className="expert-history-toggle">
              <input
                type="checkbox"
                checked={useHistory}
                onChange={(e) => {
                  void touchThread();
                  setUseHistory(e.target.checked);
                }}
              />
              <span>Использовать историю переписки</span>
              <span className="expert-history-hint">
                {useHistory ? "Агент помнит предыдущие сообщения" : "Каждое сообщение — независимое"}
              </span>
            </label>

            <label className="expert-history-toggle">
              <input
                type="checkbox"
                checked={useSearch}
                onChange={(e) => {
                  void touchThread();
                  setUseSearch(e.target.checked);
                }}
              />
              <span>Использовать актуальный поиск</span>
              <span className="expert-history-hint">
                {useSearch ? "Ищет в интернете перед ответом" : "Отвечает из знаний модели"}
              </span>
            </label>

            <div className="expert-settings-footer">
              <div className="expert-settings-footer-left">
                <span className="expert-settings-chars">{instruction.length} / 8000</span>
                <button
                  type="button"
                  className="expert-attach-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={fileLoading}
                  title="Загрузить файл (PDF, TXT, DOCX)"
                >
                  <Paperclip width={15} height={15} strokeWidth={2} />
                  {fileLoading ? "Загрузка…" : "Файл"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.md,.docx,.doc,.csv"
                  style={{ display: "none" }}
                  onChange={handleFileUpload}
                />
              </div>
              <div className="expert-settings-footer-right">
                {instruction && (
                  <button
                    type="button"
                    className="btn-secondary btn-secondary--compact"
                    onClick={() => setEditing(false)}
                    disabled={saving}
                  >
                    Отмена
                  </button>
                )}
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? "Сохранение…" : savedOk ? "✅ Сохранено" : "Сохранить"}
                </button>
              </div>
            </div>
            {error && <p className="error" style={{ marginTop: 8 }}>{error}</p>}
          </div>

        </>
      )}
    </div>
  );
}
