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
  free_llm_providers?: ProviderOption[];
  search_providers: ProviderOption[];
  vision_providers?: ProviderOption[];
  image_gen_providers?: ProviderOption[];
  prompts: PromptField[];
};

export function SettingsPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [llmProviders, setLlmProviders] = useState<ProviderOption[]>([]);
  const [freeLlmProviders, setFreeLlmProviders] = useState<ProviderOption[]>([]);
  const [searchProviders, setSearchProviders] = useState<ProviderOption[]>([]);
  const [visionProviders, setVisionProviders] = useState<ProviderOption[]>([]);
  const [imageGenProviders, setImageGenProviders] = useState<ProviderOption[]>([]);
  const [prompts, setPrompts] = useState<PromptField[]>([]);
  const [msg, setMsg] = useState("");
  const [llmRuntime, setLlmRuntime] = useState<LlmRuntime | null>(null);
  const [providersOpen, setProvidersOpen] = useState(false);
  const [promptsOpen, setPromptsOpen] = useState(false);
  const [limitsOpen, setLimitsOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);

  useEffect(() => {
    apiFetch<SettingsBundle>("/api/admin/settings").then((r) => {
      setSettings(r.settings);
      setLlmRuntime(r.llm_runtime ?? null);
      setLlmProviders(r.llm_providers);
      setFreeLlmProviders(r.free_llm_providers ?? []);
      setSearchProviders(r.search_providers);
      setVisionProviders(r.vision_providers ?? []);
      setImageGenProviders(r.image_gen_providers ?? []);
      setPrompts(r.prompts);
    });
  }, []);

  const llmProvider = String(settings.llm_provider ?? "yandex_gpt");
  const freeLlmProvider = String(settings.free_llm_provider ?? "deepseek");

  useEffect(() => {
    setPromptsOpen(false);
  }, [llmProvider]);
  const searchProvider = String(settings.search_provider ?? "yandex_search");
  const visionProvider = String(settings.vision_provider ?? "alice_vlm");
  const imageGenProvider = String(settings.image_gen_provider ?? "gigachat");

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
      guest_searches_per_day: Number(settings.guest_searches_per_day),
      free_searches_per_day: Number(settings.free_searches_per_day),
      pro_searches_per_day: Number(settings.pro_searches_per_day),
      pro_price_rub: Number(settings.pro_price_rub),
      global_yandex_requests_per_day: Number(settings.global_yandex_requests_per_day),
      maintenance_mode: Boolean(settings.maintenance_mode),
      pro_purchase_disabled: Boolean(settings.pro_purchase_disabled),
      llm_provider: llmProvider,
      free_llm_provider: freeLlmProvider,
      search_provider: searchProvider,
      vision_provider: visionProvider,
      image_gen_provider: imageGenProvider,
      free_image_gens_per_day: Number(settings.free_image_gens_per_day),
      pro_image_gens_per_day: Number(settings.pro_image_gens_per_day),
      yandex_metrica_counter_id: String(settings.yandex_metrica_counter_id ?? "").trim(),
      yandex_webmaster_verification: String(settings.yandex_webmaster_verification ?? "")
        .trim()
        .toLowerCase(),
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
      if (updated.free_llm_providers?.length) setFreeLlmProviders(updated.free_llm_providers);
      if (updated.search_providers?.length) setSearchProviders(updated.search_providers);
      if (updated.vision_providers?.length) setVisionProviders(updated.vision_providers);
      if (updated.image_gen_providers?.length) setImageGenProviders(updated.image_gen_providers);
      if (updated.prompts?.length) setPrompts(updated.prompts);
      setMsg("Сохранено");
    } catch (err) {
      const text = err instanceof Error ? err.message : "Ошибка сохранения";
      setMsg(text);
    }
  };

  return (
    <div className="settings-page">
      <h1>Настройки</h1>
      {llmRuntime?.hint && (
        <p className="error" role="alert">
          {llmRuntime.hint}
        </p>
      )}

      <form className="card settings-form" onSubmit={save}>
        <section className="settings-section settings-section--collapsible">
          <button
            type="button"
            className="settings-section-toggle"
            onClick={() => setProvidersOpen((open) => !open)}
            aria-expanded={providersOpen}
            aria-controls="settings-providers-panel"
          >
            <span className="settings-section-toggle-label">Провайдеры</span>
            <ChevronIcon expanded={providersOpen} />
          </button>
          {providersOpen && (
            <div id="settings-providers-panel" className="settings-section-panel">
              <label>
                LLM для Pro (ответы и анализ)
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
                LLM для Free (только lite)
                <select
                  value={freeLlmProvider}
                  onChange={(e) => setSettings({ ...settings, free_llm_provider: e.target.value })}
                  disabled={!can("settings:write")}
                >
                  {(freeLlmProviders.length ? freeLlmProviders : llmProviders.filter((p) => p.id === "deepseek" || p.id === "gigachat")).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                      {!p.configured ? " (не настроен)" : ""}
                    </option>
                  ))}
                </select>
                <span className="hint-inline">
                  Free: лимит free_searches_per_day, только lite-модель, без vision по фото
                </span>
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

              <label>
                Генерация картинок
                <select
                  value={imageGenProvider}
                  onChange={(e) => setSettings({ ...settings, image_gen_provider: e.target.value })}
                  disabled={!can("settings:write")}
                >
                  {(imageGenProviders.length ? imageGenProviders : [{ id: "gigachat", label: "GigaChat (text2image)", configured: true }]).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                      {!p.configured ? " (не настроен)" : ""}
                    </option>
                  ))}
                </select>
                {imageGenProviders.find((p) => p.id === imageGenProvider)?.hint && (
                  <span className="hint-inline">
                    {imageGenProviders.find((p) => p.id === imageGenProvider)?.hint}
                  </span>
                )}
                <span className="hint-inline">
                  Триггер в чате: «нарисуй», «сгенерируй картинку» и т.п. Только тариф Pro.
                </span>
              </label>
            </div>
          )}
        </section>

        {visiblePrompts.length > 0 && (
          <section className="settings-section settings-section--collapsible">
            <button
              type="button"
              className="settings-section-toggle"
              onClick={() => setPromptsOpen((open) => !open)}
              aria-expanded={promptsOpen}
              aria-controls="settings-prompts-panel"
            >
              <span className="settings-section-toggle-label">
                Промпты: {llmProviders.find((p) => p.id === llmProvider)?.label}
              </span>
              <ChevronIcon expanded={promptsOpen} />
            </button>
            {promptsOpen && (
              <div id="settings-prompts-panel" className="settings-section-panel">
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
              </div>
            )}
          </section>
        )}

        <section className="settings-section settings-section--collapsible">
          <button
            type="button"
            className="settings-section-toggle"
            onClick={() => setLimitsOpen((open) => !open)}
            aria-expanded={limitsOpen}
            aria-controls="settings-limits-panel"
          >
            <span className="settings-section-toggle-label">Лимиты и сервис</span>
            <ChevronIcon expanded={limitsOpen} />
          </button>
          {limitsOpen && (
            <div id="settings-limits-panel" className="settings-section-panel">
              <label>
                Гостевых поисков всего
                <input
                  type="number"
                  value={String(settings.guest_searches_per_day ?? "")}
                  onChange={(e) => setSettings({ ...settings, guest_searches_per_day: e.target.value })}
                  disabled={!can("settings:write")}
                />
                <span className="hint-inline">Анонимные пользователи без регистрации (за всё время гостевой сессии)</span>
              </label>
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
                Free генераций картинок / день
                <input
                  type="number"
                  min={0}
                  value={String(settings.free_image_gens_per_day ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, free_image_gens_per_day: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
                <span className="hint-inline">
                  0 — генерация только на Pro (рекомендуется)
                </span>
              </label>
              <label>
                Гостевых генераций документов (за жизнь)
                <input
                  type="number"
                  min={0}
                  value={String(settings.guest_doc_gens_lifetime ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, guest_doc_gens_lifetime: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
              </label>
              <label>
                Free генераций документов / день
                <input
                  type="number"
                  min={0}
                  value={String(settings.free_doc_gens_per_day ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, free_doc_gens_per_day: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
              </label>
              <label>
                Pro генераций документов / день
                <input
                  type="number"
                  min={0}
                  value={String(settings.pro_doc_gens_per_day ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, pro_doc_gens_per_day: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
              </label>
              <label>
                Хранение сгенерированных документов (часов)
                <input
                  type="number"
                  min={1}
                  value={String(settings.generated_doc_ttl_hours ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, generated_doc_ttl_hours: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
              </label>
              <label>
                Pro генераций картинок / день
                <input
                  type="number"
                  min={0}
                  value={String(settings.pro_image_gens_per_day ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, pro_image_gens_per_day: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
              </label>
              <label>
                Цена Pro, ₽ / месяц
                <input
                  type="number"
                  min={1}
                  value={String(settings.pro_price_rub ?? "")}
                  onChange={(e) => setSettings({ ...settings, pro_price_rub: e.target.value })}
                  disabled={!can("settings:write")}
                />
                <span className="hint-inline">Сумма списания в ЮKassa и на странице профиля</span>
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
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={Boolean(settings.pro_purchase_disabled)}
                  onChange={(e) =>
                    setSettings({ ...settings, pro_purchase_disabled: e.target.checked })
                  }
                  disabled={!can("settings:write")}
                />
                Запрет покупки подписки Pro
                <span className="hint-inline">
                  Кнопка «Перейти на Pro» покажет сообщение; оплата через ЮKassa заблокирована
                </span>
              </label>
            </div>
          )}
        </section>

        <section className="settings-section settings-section--collapsible">
          <button
            type="button"
            className="settings-section-toggle"
            onClick={() => setAnalyticsOpen((open) => !open)}
            aria-expanded={analyticsOpen}
            aria-controls="settings-analytics-panel"
          >
            <span className="settings-section-toggle-label">Аналитика и SEO</span>
            <ChevronIcon expanded={analyticsOpen} />
          </button>
          {analyticsOpen && (
            <div id="settings-analytics-panel" className="settings-section-panel">
              <label>
                Яндекс.Метрика — ID счётчика
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="например, 12345678"
                  value={String(settings.yandex_metrica_counter_id ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, yandex_metrica_counter_id: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
                <span className="hint-inline">
                  Только цифры. Счётчик подключается на сайте после согласия пользователя на cookie.
                  Пустое поле — Метрика отключена.
                </span>
              </label>
              <label>
                Яндекс.Вебмастер — код верификации
                <input
                  type="text"
                  placeholder="например, 7256c8302424cadd"
                  value={String(settings.yandex_webmaster_verification ?? "")}
                  onChange={(e) =>
                    setSettings({ ...settings, yandex_webmaster_verification: e.target.value })
                  }
                  disabled={!can("settings:write")}
                />
                <span className="hint-inline">
                  Код из HTML-файла (строка «Verification: …»). После сохранения файл будет доступен по
                  адресу{" "}
                  {String(settings.yandex_webmaster_verification ?? "").trim() ? (
                    <code>
                      https://glosix.ru/yandex_
                      {String(settings.yandex_webmaster_verification).trim().toLowerCase()}.html
                    </code>
                  ) : (
                    <code>https://glosix.ru/yandex_&lt;код&gt;.html</code>
                  )}
                  . Укажите этот URL в Вебмастере.
                </span>
              </label>
            </div>
          )}
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
    </div>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`settings-chevron${expanded ? " settings-chevron--expanded" : ""}`}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
