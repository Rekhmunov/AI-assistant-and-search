import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type TemplateInfo = {
  id: string;
  title: string;
  mode: "all" | "users";
  user_ids: string[];
};

type UserHint = {
  id: string;
  email: string | null;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
};

function userLabel(u: UserHint): string {
  const name = [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
  if (u.email) return name ? `${u.email} (${name})` : u.email;
  if (u.username) return name ? `@${u.username} (${name})` : `@${u.username}`;
  return name || u.id.slice(0, 8);
}

export function AgentTemplatesPage() {
  const { can } = useAuth();
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [msg, setMsg] = useState("");
  const canWrite = can("settings:write");

  useEffect(() => {
    apiFetch<TemplateInfo[]>("/api/admin/agent-templates").then(setTemplates).catch(() => {});
  }, []);

  const updateTemplate = async (id: string, mode: "all" | "users", user_ids: string[]) => {
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
  onSave: (mode: "all" | "users", user_ids: string[]) => void;
}) {
  const [mode, setMode] = useState<"all" | "users">(template.mode);
  const [selectedUsers, setSelectedUsers] = useState<UserHint[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<UserHint[]>([]);
  const [searching, setSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [dirty, setDirty] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Загружаем данные уже выбранных пользователей
  useEffect(() => {
    if (template.user_ids.length === 0) {
      setSelectedUsers([]);
      return;
    }
    Promise.all(
      template.user_ids.map((uid) =>
        apiFetch<UserHint[]>(`/api/admin/users?search=${uid}&limit=5`)
          .then((users) => users.find((u) => u.id === uid) ?? null)
          .catch(() => null)
      )
    ).then((results) => {
      setSelectedUsers(results.filter(Boolean) as UserHint[]);
    });
  }, [template.id, template.user_ids.join(",")]);

  // Закрывать дропдаун при клике снаружи
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSearchChange = (v: string) => {
    setSearchQuery(v);
    setShowDropdown(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!v.trim()) {
      setSearchResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await apiFetch<UserHint[]>(
          `/api/admin/users?search=${encodeURIComponent(v.trim())}&limit=10`
        );
        setSearchResults(results.filter((r) => !selectedUsers.some((s) => s.id === r.id)));
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  const addUser = (user: UserHint) => {
    setSelectedUsers((prev) => [...prev, user]);
    setSearchQuery("");
    setSearchResults([]);
    setShowDropdown(false);
    setDirty(true);
  };

  const removeUser = (id: string) => {
    setSelectedUsers((prev) => prev.filter((u) => u.id !== id));
    setDirty(true);
  };

  const handleModeChange = (v: "all" | "users") => {
    setMode(v);
    setDirty(true);
  };

  const handleSave = () => {
    onSave(mode, mode === "all" ? [] : selectedUsers.map((u) => u.id));
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
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
          <span style={{ fontWeight: 500, fontSize: "0.9rem" }}>Пользователи</span>

          {/* Чипы выбранных пользователей */}
          {selectedUsers.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {selectedUsers.map((u) => (
                <span
                  key={u.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    background: "var(--accent, #4f6ef7)",
                    color: "#fff",
                    borderRadius: 20,
                    padding: "4px 12px",
                    fontSize: "0.85rem",
                  }}
                >
                  {userLabel(u)}
                  {canWrite && (
                    <button
                      type="button"
                      onClick={() => removeUser(u.id)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#fff",
                        cursor: "pointer",
                        padding: 0,
                        lineHeight: 1,
                        fontSize: "1rem",
                        opacity: 0.8,
                      }}
                      aria-label="Удалить"
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* Поиск */}
          {canWrite && (
            <div ref={searchRef} style={{ position: "relative", maxWidth: 420 }}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                onFocus={() => searchQuery && setShowDropdown(true)}
                placeholder="Поиск по email, имени…"
                style={{ width: "100%", boxSizing: "border-box" }}
              />
              {showDropdown && (searchResults.length > 0 || searching) && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: 0,
                    right: 0,
                    background: "var(--bg-card, #fff)",
                    border: "1px solid var(--border, #ddd)",
                    borderRadius: 6,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                    zIndex: 100,
                    maxHeight: 240,
                    overflowY: "auto",
                  }}
                >
                  {searching && (
                    <div style={{ padding: "10px 14px", color: "var(--muted)", fontSize: "0.85rem" }}>
                      Поиск…
                    </div>
                  )}
                  {searchResults.map((u) => (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => addUser(u)}
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        padding: "9px 14px",
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        fontSize: "0.9rem",
                        borderBottom: "1px solid var(--border, #eee)",
                      }}
                    >
                      {userLabel(u)}
                    </button>
                  ))}
                  {!searching && searchResults.length === 0 && (
                    <div style={{ padding: "10px 14px", color: "var(--muted)", fontSize: "0.85rem" }}>
                      Не найдено
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {canWrite && dirty && (
        <button type="button" className="btn btn--primary" onClick={handleSave}>
          Сохранить
        </button>
      )}
    </div>
  );
}
