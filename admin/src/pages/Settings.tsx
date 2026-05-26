import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type ProviderOption = {
  id: string;
  label: string;
  configured: boolean;
  hint?: string | null;
};

type PromptField = {
  id: string;
  label: string;
  group: string;
  provider: string;
  setting_key: string;
  description?: string;
  rows: number;
  value: string;
  default: string;
};

type SettingsBundle = {
  settings: Record<string, unknown>;
  llm_providers: ProviderOption[];
  search_providers: ProviderOption[];
  prompts: PromptField[];
};

export function SettingsPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [llmProviders, setLlmProviders] = useState<ProviderOption[]>([]);
  const [searchProviders, setSearchProviders] = useState<ProviderOption[]>([]);
  const [prompts, setPrompts] = useState<PromptField[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    apiFetch<SettingsBundle>("/api/admin/settings").then((r) => {
      setSettings(r.settings);
      setLlmProviders(r.llm_providers);
      setSearchProviders(r.search_providers);
      setPrompts(r.prompts);
    });
  }, []);

  const llmProvider = String(settings.llm_provider ?? "yandex_gpt");
  const searchProvider = String(settings.search_provider ?? "yandex_search");

  const visiblePrompts = useMemo(
    () => prompts.filter((p) => p.provider === llmProvider),
    [prompts, llmProvider],
  );

  const promptsByGroup = useMemo(() => {
    const map = new Map<string, PromptField[]>();
    for (const p of visiblePrompts) {
      const list = map.get(p.group) ?? [];
      list.push(p);
      map.set(p.group, list);
    }
    return map;
  }, [visiblePrompts]);

  const setPromptValue = (settingKey: string, value: string) => {
    setSettings((prev) => ({ ...prev, [settingKey]: value }));
    setPrompts((prev) =>
      prev.map((p) => (p.setting_key === settingKey ? { ...p, value } : p)),
    );
  };

  const resetPrompt = (p: PromptField) => {
    setPromptValue(p.setting_key, p.default);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const payload: Record<string, unknown> = {
      free_searches_per_day: Number(settings.free_searches_per_day),
      pro_searches_per_day: Number(settings.pro_searches_per_day),
      global_yandex_requests_per_day: Number(settings.global_yandex_requests_per_day),
      maintenance_mode: Boolean(settings.maintenance_mode),
      bot_welcome_text: String(settings.bot_welcome_text),
      llm_provider: llmProvider,
      search_provider: searchProvider,
    };
    for (const p of prompts) {
      payload[p.setting_key] = String(settings[p.setting_key] ?? p.value);
    }
    const updated = await apiFetch<SettingsBundle>("/api/admin/settings", {
      method: "PATCH",
      body: JSON.stringify({ settings: payload }),
    });
    setSettings(updated.settings);
    setPrompts(updated.prompts);
    setMsg("Сохранено");
  };

  return (
    <div className="settings-page">
      <h1>Настройки</h1>
      <p className="hint">
        Секреты (BOT_TOKEN, Yandex API, JWT) — только в .env. Lite/Pro для ответов выбирает код по типу
        запроса.
      </p>

      <form className="card settings-form" onSubmit={save}>
        <section className="settings-section">
          <h2 className="settings-section-title">Провайдеры</h2>
          <label>
            LLM (ответы и анализ)
            <select
              value={llmProvider}
              onChange={(e) => setSettings({ ...settings, llm_provider: e.target.value })}
              disabled={!can("settings:write")}
            >
              {llmProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {!p.configured ? " (не настроен)" : ""}
                </option>
              ))}
            </select>
            {llmProviders.find((p) => p.id === llmProvider)?.hint && (
              <span className="hint-inline">
                {llmProviders.find((p) => p.id === llmProvider)?.hint}
              </span>
            )}
          </label>

          <label>
            Веб-поиск
            <select
              value={searchProvider}
              onChange={(e) => setSettings({ ...settings, search_provider: e.target.value })}
              disabled={!can("settings:write")}
            >
              {searchProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {!p.configured ? " (не настроен)" : ""}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">
            У Yandex Search нет текстового промпта — только HTTP-запрос. Запросы в поиск формирует
            блок «Пайплайн поиска» ниже (rewriter).
          </p>
        </section>

        {visiblePrompts.length > 0 && (
          <section className="settings-section">
            <h2 className="settings-section-title">Промпты: {llmProviders.find((p) => p.id === llmProvider)?.label}</h2>
            {[...promptsByGroup.entries()].map(([group, items]) => (
              <div key={group} className="settings-prompt-group">
                <h3 className="settings-prompt-group-title">{group}</h3>
                {items.map((p) => (
                  <label key={p.id} className="settings-prompt-label">
                    <span className="settings-prompt-head">
                      <span>{p.label}</span>
                      {can("settings:write") && (
                        <button
                          type="button"
                          className="btn-link"
                          onClick={() => resetPrompt(p)}
                        >
                          Сбросить к умолчанию
                        </button>
                      )}
                    </span>
                    {p.description && <span className="hint-inline">{p.description}</span>}
                    <textarea
                      rows={p.rows}
                      value={String(settings[p.setting_key] ?? p.value)}
                      onChange={(e) => setPromptValue(p.setting_key, e.target.value)}
                      disabled={!can("settings:write")}
                      spellCheck={false}
                    />
                  </label>
                ))}
              </div>
            ))}
          </section>
        )}

        <section className="settings-section">
          <h2 className="settings-section-title">Лимиты и сервис</h2>
          <label>
            Free поисков / день
            <input
              type="number"
              value={String(settings.free_searches_per_day ?? "")}
              onChange={(e) => setSettings({ ...settings, free_searches_per_day: e.target.value })}
              disabled={!can("settings:write")}
            />
          </label>
          <label>
            Pro поисков / день
            <input
              type="number"
              value={String(settings.pro_searches_per_day ?? "")}
              onChange={(e) => setSettings({ ...settings, pro_searches_per_day: e.target.value })}
              disabled={!can("settings:write")}
            />
          </label>
          <label>
            Yandex запросов / день (глобально)
            <input
              type="number"
              value={String(settings.global_yandex_requests_per_day ?? "")}
              onChange={(e) =>
                setSettings({ ...settings, global_yandex_requests_per_day: e.target.value })
              }
              disabled={!can("settings:write")}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={Boolean(settings.maintenance_mode)}
              onChange={(e) => setSettings({ ...settings, maintenance_mode: e.target.checked })}
              disabled={!can("settings:write")}
            />
            Режим обслуживания (блокирует поиск)
          </label>
          <label>
            Текст приветствия бота
            <textarea
              rows={3}
              value={String(settings.bot_welcome_text ?? "")}
              onChange={(e) => setSettings({ ...settings, bot_welcome_text: e.target.value })}
              disabled={!can("settings:write")}
            />
          </label>
        </section>

        {can("settings:write") && (
          <button type="submit" className="btn-primary">
            Сохранить
          </button>
        )}
      </form>

      {msg && <p className="ok">{msg}</p>}
      <p>
        Yandex: {settings.yandex_configured ? "настроен" : "mock"} · Среда: {String(settings.environment)}
      </p>
    </div>
  );
}
