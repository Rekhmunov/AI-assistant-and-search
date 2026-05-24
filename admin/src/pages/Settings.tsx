import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

export function SettingsPage() {
  const { can } = useAuth();
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    apiFetch<{ settings: Record<string, unknown> }>("/api/admin/settings").then((r) => setSettings(r.settings));
  }, []);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    await apiFetch("/api/admin/settings", {
      method: "PATCH",
      body: JSON.stringify({
        settings: {
          free_searches_per_day: Number(settings.free_searches_per_day),
          pro_searches_per_day: Number(settings.pro_searches_per_day),
          global_yandex_requests_per_day: Number(settings.global_yandex_requests_per_day),
          maintenance_mode: Boolean(settings.maintenance_mode),
          bot_welcome_text: String(settings.bot_welcome_text),
        },
      }),
    });
    setMsg("Сохранено");
  };

  return (
    <div>
      <h1>Настройки</h1>
      <p className="hint">Секреты (BOT_TOKEN, Yandex, JWT) задаются только в .env на сервере.</p>
      <form className="card" onSubmit={save}>
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
            onChange={(e) => setSettings({ ...settings, global_yandex_requests_per_day: e.target.value })}
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
