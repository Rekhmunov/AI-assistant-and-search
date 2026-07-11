import { useState, useEffect } from "react";
import { useAuthStore } from "../store/authStore";
import { useTouchThread } from "../hooks/useTouchThread";

const API_BASE = import.meta.env.VITE_API_URL || "";

const PLACEHOLDER = `Примеры инструкций:

Ты — опытный копирайтер. Пиши продающие тексты в дружелюбном тоне. Используй короткие абзацы и заголовки. Всегда предлагай несколько вариантов.

Ты — юрист, специализирующийся на российском праве. Отвечай точно, ссылайся на статьи законов, предупреждай о рисках. Не давай окончательных юридических заключений.

Ты — ментор по продуктовому менеджменту. Задавай уточняющие вопросы, помогай структурировать мысли, давай конкретные фреймворки.`;

type Props = {
  threadId: string;
  initialConfig?: Record<string, unknown>;
};

export function ExpertSettingsPanel({ threadId, initialConfig }: Props) {
  const token = useAuthStore((s) => s.token);
  const touchThread = useTouchThread(threadId, token);
  const [instruction, setInstruction] = useState(
    String(initialConfig?.expert_instruction ?? "")
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/agent/threads/${threadId}/config`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({ expert_instruction: instruction }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e.message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="expert-settings-panel">
      <div className="expert-settings-header">
        <h3 className="expert-settings-title">Инструкция</h3>
        <p className="expert-settings-sub">
          Задайте роль, стиль ответов или правила — агент будет следовать им в каждом сообщении.
        </p>
      </div>

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
        />
        <div className="expert-settings-footer">
          <span className="expert-settings-chars">
            {instruction.length} / 8000
          </span>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Сохранение…" : saved ? "✅ Сохранено" : "Сохранить"}
          </button>
        </div>
        {error && <p className="error" style={{ marginTop: 8 }}>{error}</p>}
      </div>

      <div className="expert-settings-examples">
        <p className="expert-settings-examples-title">Идеи для инструкций:</p>
        <div className="expert-settings-chips">
          {[
            "Опытный копирайтер",
            "Юрист (РФ)",
            "SEO-специалист",
            "Ментор по продукту",
            "Переводчик EN↔RU",
            "Редактор текстов",
            "Финансовый советник",
            "Программист Python",
          ].map((label) => (
            <button
              key={label}
              type="button"
              className="expert-chip"
              onClick={() => {
                void touchThread();
                setInstruction((prev) =>
                  prev ? `${prev}\n\nТы — ${label}.` : `Ты — ${label}.`
                );
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
