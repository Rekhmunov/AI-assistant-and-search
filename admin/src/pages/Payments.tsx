import { useEffect, useState } from "react";
import { apiFetch } from "../api";

interface Sub {
  id: string;
  user_id: string;
  yookassa_payment_id: string | null;
  status: string;
  amount_rub: number;
  created_at: string;
  activated_at: string | null;
  user_email_hint: string | null;
}

export function PaymentsPage() {
  const [items, setItems] = useState<Sub[]>([]);

  useEffect(() => {
    apiFetch<Sub[]>("/api/admin/payments/subscriptions").then(setItems);
  }, []);

  return (
    <div>
      <h1>Платежи / подписки</h1>
      <table className="table">
        <thead>
          <tr>
            <th>Пользователь</th>
            <th>Статус</th>
            <th>Сумма</th>
            <th>Payment ID</th>
            <th>Создан</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <td>{s.user_email_hint}</td>
              <td>{s.status}</td>
              <td>{s.amount_rub} ₽</td>
              <td>{s.yookassa_payment_id || "—"}</td>
              <td>{new Date(s.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
