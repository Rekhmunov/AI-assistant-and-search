import { useEffect, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type TemplateInfo = {
  id: string;
  title: string;
  mode: "all" | "users";
  user_ids: number[];
};

export function AgentTemplatesPage() {
  const { can } = useAuth();
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [msg, setMsg] = useState("");
  const canWrite = can("settings:write");

  useEffect(() => {
    apiFetch<TemplateInfo[]>("/api/admin/agent-templates").then(setTemplates).catch(() => {});
  }, []);

  const updateTemplate = async (id: string, mode: "all" | "users", user_ids: number[]) => {
    setMsg("");
    try {
      const updated = await apiFetch<TemplateInfo[]>(`/api/admin/agent-templates/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ mode, user_ids }),
      });
      setTemplates(updated);
      setMsg("Сохранено");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка сохранения");
    }
  };

  return (
    <div className="page-content">
      <h1>Агенты</h1>
      <p className="hint-inline" style={{ marginBottom: 20 }}>
        Управляйте видимостью агентов для пользователей. «Все» — агент доступен каждому.
        «Конкретные пользователи» — только перечисленным по ID.
      </p>

      {msg && (
        <p className={msg === "Сохранено" ? "success" : "error"} role="alert">
          {msg}
        </p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {templates.map((tmpl) => (
          <TemplateCard
            key={tmpl.id}
            template={tmpl}
            canWrite={canWrite}
            onSave={(mode, user_ids) => updateTemplate(tmpl.id, mode, user_ids)}
          />
        ))}
      </div>
    </div>
  );
}

function TemplateCard({
  template,
  canWrite,
  onSave,
}: {
  template: TemplateInfo;
  canWrite: boolean;
  onSave: (mode: "all" | "users", user_ids: number[]) => void;
}) {
  const [mode, setMode] = useState<"all" | "users">(template.mode);
  const [userIdsText, setUserIdsText] = useState(template.user_ids.join(", "));
  const [dirty, setDirty] = useState(false);

  const handleModeChange = (v: "all" | "users") => {
    setMode(v);
    setDirty(true);
  };

  const handleUserIdsChange = (v: string) => {
    setUserIdsText(v);
    setDirty(true);
  };

  const handleSave = () => {
    const ids = userIdsText
      .split(/[\s,;]+/)
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n) && n > 0);
    onSave(mode, mode === "all" ? [] : ids);
    setDirty(false);
  };

  return (
    <div className="card" style={{ padding: "20px 24px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <strong style={{ fontSize: "1.05rem" }}>{template.title}</strong>
        <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>id: {template.id}</span>
      </div>

      <label style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
        <span style={{ fontWeight: 500, fontSize: "0.9rem" }}>Кому показывать</span>
        <select
          value={mode}
          onChange={(e) => handleModeChange(e.target.value as "all" | "users")}
          disabled={!canWrite}
          style={{ maxWidth: 320 }}
        >
          <option value="all">Все пользователи</option>
          <option value="users">Конкретные пользователи</option>
        </select>
      </label>

      {mode === "users" && (
        <label style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
          <span style={{ fontWeight: 500, fontSize: "0.9rem" }}>
            ID пользователей (через запятую)
          </span>
          <textarea
            value={userIdsText}
            onChange={(e) => handleUserIdsChange(e.target.value)}
            disabled={!canWrite}
            rows={2}
            placeholder="123, 456, 789"
            style={{ maxWidth: 420, resize: "vertical" }}
          />
          <span className="hint-inline">
            Найти ID можно в разделе Пользователи. Агент будет виден только этим аккаунтам.
          </span>
        </label>
      )}

      {canWrite && dirty && (
        <button type="button" className="btn btn--primary" onClick={handleSave}>
          Сохранить
        </button>
      )}
    </div>
  );
}
