import { useEffect, useState } from "react";
import { apiFetch } from "../api";

interface DashboardMetrics {
  users_total: number;
  users_new_7d: number;
  users_pro: number;
  users_active_24h: number;
  broadcasts_total: number;
  messages_today: number;
  searches_today_estimate: number;
  yandex_configured: boolean;
  redis_ok: boolean;
  maintenance_mode: boolean;
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<DashboardMetrics>("/api/admin/dashboard")
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p>Загрузка метрик…</p>;

  return (
    <div>
      <h1>Дашборд</h1>
      <div className="grid">
        <div className="stat-card">
          <span>Пользователей</span>
          <strong>{data.users_total}</strong>
        </div>
        <div className="stat-card">
          <span>Новых за 7 дней</span>
          <strong>{data.users_new_7d}</strong>
        </div>
        <div className="stat-card">
          <span>Pro</span>
          <strong>{data.users_pro}</strong>
        </div>
        <div className="stat-card">
          <span>Активных 24ч</span>
          <strong>{data.users_active_24h}</strong>
        </div>
        <div className="stat-card">
          <span>Сообщений сегодня</span>
          <strong>{data.messages_today}</strong>
        </div>
        <div className="stat-card">
          <span>Рассылок</span>
          <strong>{data.broadcasts_total}</strong>
        </div>
      </div>
      <h2>Система</h2>
      <ul className="status-list">
        <li className={data.yandex_configured ? "ok" : "warn"}>Yandex API: {data.yandex_configured ? "настроен" : "mock"}</li>
        <li className={data.redis_ok ? "ok" : "bad"}>Redis: {data.redis_ok ? "ok" : "ошибка"}</li>
        <li className={data.maintenance_mode ? "warn" : "ok"}>
          Режим обслуживания: {data.maintenance_mode ? "включён" : "выключен"}
        </li>
      </ul>
    </div>
  );
}
