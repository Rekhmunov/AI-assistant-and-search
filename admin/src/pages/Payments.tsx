import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

interface Sub {
  id: string;
  user_id: string;
  yookassa_payment_id: string | null;
  status: string;
  status_label: string;
  amount_rub: number;
  created_at: string;
  activated_at: string | null;
  user_email_hint: string | null;
}

export function PaymentsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Sub[]>([]);
  const [msg, setMsg] = useState("");
  const [syncingUserId, setSyncingUserId] = useState<string | null>(null);

  const load = () => {
    apiFetch<Sub[]>("/api/admin/payments/subscriptions").then(setItems);
  };

  useEffect(load, []);

  const syncProPayment = async (userId: string) => {
    setMsg("");
    setSyncingUserId(userId);
    try {
      const result = await apiFetch<{ ok: boolean; message?: string; payment_id?: string; source?: string }>(
        `/api/admin/users/${userId}/sync-pro-payment`,
        { method: "POST" }
      );
      if (result.ok) {
        setMsg(
          result.payment_id
            ? `Pro восстановлен для пользователя (платёж ${result.payment_id})`
            : "Pro уже активен у пользователя"
        );
        load();
        return;
      }
      setMsg(result.message || "Успешная оплата не найдена в ЮKassa");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Не удалось синхронизировать оплату");
    } finally {
      setSyncingUserId(null);
    }
  };

  return (
    <div>
      <h1>Платежи / подписки</h1>
      <p className="hint">
        Если пользователь оплатил Pro, но тариф не обновился — откройте его профиль или нажмите{" "}
        <strong>«Восстановить Pro»</strong> в таблице ниже.
      </p>
      {msg && <p className="ok">{msg}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>Пользователь</th>
            <th>Статус</th>
            <th>Сумма</th>
            <th>Payment ID</th>
            <th>Создан</th>
            {can("payments:write") && <th>Действия</th>}
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td>
                <Link to={`/users/${s.user_id}`}>{s.user_email_hint || "—"}</Link>
              </td>
              <td>{s.status_label || s.status}</td>
              <td>{s.amount_rub} ₽</td>
              <td>{s.yookassa_payment_id || "—"}</td>
              <td>{new Date(s.created_at).toLocaleString()}</td>
              {can("payments:write") && (
                <td>
                  <button
                    type="button"
                    className="btn-secondary btn-secondary--compact"
                    disabled={syncingUserId === s.user_id}
                    onClick={() => void syncProPayment(s.user_id)}
                  >
                    {syncingUserId === s.user_id ? "…" : "Восстановить Pro"}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
