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

type LlmRuntime = {
  active_provider: string;
  anthropic_api_key_loaded: boolean;
  anthropic_key_suffix?: string | null;
  anthropic_mock_active: boolean;
  deepseek_api_key_loaded?: boolean;
  deepseek_key_suffix?: string | null;
  deepseek_mock_active?: boolean;
  gigachat_credentials_loaded?: boolean;
  gigachat_mock_active?: boolean;
  hint?: string | null;
};

type SettingsBundle = {
  settings: Record<string, unknown>;
  llm_runtime?: LlmRuntime | null;
  llm_providers: ProviderOption[];
  search_providers: ProviderOption[];
  vision_providers?: ProviderOption[];
  prompts: PromptField[];
};

export function SettingsPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [llmProviders, setLlmProviders] = useState<ProviderOption[]>([]);
  const [searchProviders, setSearchProviders] = useState<ProviderOption[]>([]);
  const [visionProviders, setVisionProviders] = useState<ProviderOption[]>([]);
  const [prompts, setPrompts] = useState<PromptField[]>([]);
  const [msg, setMsg] = useState("");
  const [llmRuntime, setLlmRuntime] = useState<LlmRuntime | null>(null);
  const [probeMsg, setProbeMsg] = useState("");
  const [deepseekProbeMsg, setDeepseekProbeMsg] = useState("");
  const [gigachatProbeMsg, setGigachatProbeMsg] = useState("");

  useEffect(() => {
    apiFetch<SettingsBundle>("/api/admin/settings").then((r) => {
      setSettings(r.settings);
      setLlmRuntime(r.llm_runtime ?? null);
      setLlmProviders(r.llm_providers);
      setSearchProviders(r.search_providers);
      setVisionProviders(r.vision_providers ?? []);
      setPrompts(r.prompts);
    });
  }, []);

  const llmProvider = String(settings.llm_provider ?? "yandex_gpt");
  const searchProvider = String(settings.search_provider ?? "yandex_search");
  const visionProvider = String(settings.vision_provider ?? "gigachat");

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
    setMsg("");
    const payload: Record<string, unknown> = {
      free_searches_per_day: Number(settings.free_searches_per_day),
      pro_searches_per_day: Number(settings.pro_searches_per_day),
      global_yandex_requests_per_day: Number(settings.global_yandex_requests_per_day),
      maintenance_mode: Boolean(settings.maintenance_mode),
      bot_welcome_text: String(settings.bot_welcome_text),
      llm_provider: llmProvider,
      search_provider: searchProvider,
      vision_provider: visionProvider,
    };
    for (const p of visiblePrompts) {
      payload[p.setting_key] = String(settings[p.setting_key] ?? p.value);
    }
    try {
      const updated = await apiFetch<SettingsBundle>("/api/admin/settings", {
        method: "PATCH",
        body: JSON.stringify({ settings: payload }),
      });
      setSettings(updated.settings ?? {});
      if (updated.llm_runtime) setLlmRuntime(updated.llm_runtime);
      if (updated.llm_providers?.length) setLlmProviders(updated.llm_providers);
      if (updated.search_providers?.length) setSearchProviders(updated.search_providers);
      if (updated.vision_providers?.length) setVisionProviders(updated.vision_providers);
      if (updated.prompts?.length) setPrompts(updated.prompts);
      setMsg("Сохранено");
    } catch (err) {
      const text = err instanceof Error ? err.message : "Ошибка сохранения";
      setMsg(text);
    }
  };

  const runAnthropicProbe = async () => {
    setProbeMsg("Проверка…");
    try {
      const r = await apiFetch<{
        ok: boolean;
        key_suffix?: string;
        message: string;
      }>("/api/admin/settings/probe-anthropic", { method: "POST" });
      setProbeMsg(
        r.ok
          ? `${r.message} (суффикс ключа …${r.key_suffix ?? "?"})`
          : r.message,
      );
    } catch (err) {
      setProbeMsg(err instanceof Error ? err.message : "Ошибка проверки");
    }
  };

  const runGigachatProbe = async () => {
    setGigachatProbeMsg("Проверка…");
    try {
      const r = await apiFetch<{
        ok: boolean;
        credentials_suffix?: string;
        message: string;
      }>("/api/admin/settings/probe-gigachat", { method: "POST" });
      setGigachatProbeMsg(
        r.ok
          ? `${r.message} (суффикс credentials …${r.credentials_suffix ?? "?"})`
          : r.message,
      );
    } catch (err) {
      setGigachatProbeMsg(err instanceof Error ? err.message : "Ошибка проверки");
    }
  };

  const runDeepseekProbe = async () => {
    setDeepseekProbeMsg("Проверка…");
    try {
      const r = await apiFetch<{
        ok: boolean;
        key_suffix?: string;
        message: string;
      }>("/api/admin/settings/probe-deepseek", { method: "POST" });
      setDeepseekProbeMsg(
        r.ok
          ? `${r.message} (суффикс ключа …${r.key_suffix ?? "?"})`
          : r.message,
      );
    } catch (err) {
      setDeepseekProbeMsg(err instanceof Error ? err.message : "Ошибка проверки");
    }
  };

  return (
    <div className="settings-page">
      <h1>Настройки</h1>
      <p className="hint">
        Секреты (BOT_TOKEN, Yandex API, Anthropic, DeepSeek, GigaChat) — только в .env на сервере. Ключ из чата Cursor не
        используется. После смены .env: force-recreate backend. Lite/Pro выбирает код по типу запроса.
      </p>
      {llmRuntime?.hint && (
        <p className="error" role="alert">
          {llmRuntime.hint}
        </p>
      )}

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

          <label>
            LLM для фото (vision)
            <select
              value={visionProvider}
              onChange={(e) => setSettings({ ...settings, vision_provider: e.target.value })}
              disabled={!can("settings:write")}
            >
              {visionProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {!p.configured ? " (не настроен)" : ""}
                </option>
              ))}
            </select>
            {visionProviders.find((p) => p.id === visionProvider)?.hint && (
              <span className="hint-inline">
                {visionProviders.find((p) => p.id === visionProvider)?.hint}
              </span>
            )}
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

      {msg && (
        <p className={msg === "Сохранено" ? "ok" : "error"} role="alert">
          {msg}
        </p>
      )}
      <p>
        Yandex: {settings.yandex_configured ? "настроен" : "mock"} · Claude в .env:{" "}
        {settings.anthropic_configured ? "да" : "нет"}
        {llmRuntime?.anthropic_key_suffix
          ? ` (…${llmRuntime.anthropic_key_suffix})`
          : ""}{" "}
        · DeepSeek в .env: {settings.deepseek_configured ? "да" : "нет"}
        {llmRuntime?.deepseek_key_suffix
          ? ` (…${llmRuntime.deepseek_key_suffix})`
          : ""}{" "}
        · GigaChat в .env: {settings.gigachat_configured ? "да" : "нет"} · Активный LLM:{" "}
        {llmRuntime?.active_provider ?? llmProvider}
        {llmRuntime?.anthropic_mock_active ||
        llmRuntime?.deepseek_mock_active ||
        llmRuntime?.gigachat_mock_active
          ? " · mock, API не вызывается"
          : ""}{" "}
        · Среда:{" "}
        {String(settings.environment)}
      </p>
      {can("settings:read") && (
        <p>
          <button type="button" className="btn-link" onClick={() => void runAnthropicProbe()}>
            Проверить Claude (тестовый запрос из .env)
          </button>
          {probeMsg && <span className="hint-inline"> {probeMsg}</span>}
        </p>
      )}
      {can("settings:read") && (
        <p>
          <button type="button" className="btn-link" onClick={() => void runDeepseekProbe()}>
            Проверить DeepSeek (lite + pro из .env)
          </button>
          {deepseekProbeMsg && <span className="hint-inline"> {deepseekProbeMsg}</span>}
        </p>
      )}
      {can("settings:read") && (
        <p>
          <button type="button" className="btn-link" onClick={() => void runGigachatProbe()}>
            Проверить GigaChat (OAuth, lite + pro из .env)
          </button>
          {gigachatProbeMsg && <span className="hint-inline"> {gigachatProbeMsg}</span>}
        </p>
      )}
    </div>
  );
}
