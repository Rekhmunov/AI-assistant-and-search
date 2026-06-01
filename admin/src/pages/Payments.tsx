import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
  user_email: string | null;
  user_max_user_id: number | null;
  user_contact_label: string | null;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU");
}

function contactLabel(sub: Sub): string {
  if (sub.user_contact_label) return sub.user_contact_label;
  const email = sub.user_email?.trim() || "не привязан";
  const max = sub.user_max_user_id != null ? String(sub.user_max_user_id) : "не привязан";
  return `email: ${email}, max: ${max}`;
}

export function PaymentsPage() {
  const { can } = useAuth();
  const [items, setItems] = useState<Sub[]>([]);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncingUserId, setSyncingUserId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const canWrite = can("payments:write");

  const load = useCallback(async (searchTerm: string) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (searchTerm.trim()) params.set("search", searchTerm.trim());
      const data = await apiFetch<Sub[]>(`/api/admin/payments/subscriptions?${params}`);
      setItems(Array.isArray(data) ? data : []);
      setSelected(new Set());
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "Не удалось загрузить подписки");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(query);
  }, [load, query]);

  const allSelected = items.length > 0 && selected.size === items.length;
  const someSelected = selected.size > 0;

  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(items.map((item) => item.id)));
  };

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setQuery(search);
  };

  const syncProPayment = async (userId: string) => {
    setMsg("");
    setError("");
    setSyncingUserId(userId);
    try {
      const result = await apiFetch<{
        ok: boolean;
        plan?: string;
        message?: string;
        payment_id?: string;
        source?: string;
        already_active?: boolean;
      }>(`/api/admin/users/${userId}/sync-pro-payment`, { method: "POST" });
      if (result.ok && (result.plan === "pro" || result.already_active)) {
        setMsg(
          result.payment_id
            ? `Pro восстановлен для пользователя (платёж ${result.payment_id})`
            : "Pro уже активен у пользователя"
        );
        await load(query);
        return;
      }
      if (result.ok) {
        setError("Синхронизация прошла, но тариф пользователя остался Free");
        await load(query);
        return;
      }
      setError(result.message || "Успешная оплата не найдена в ЮKassa");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось синхронизировать оплату");
    } finally {
      setSyncingUserId(null);
    }
  };

  const deleteSubscriptions = async (ids: string[]) => {
    if (!ids.length) return;
    const label = ids.length === 1 ? "эту запись" : `${ids.length} записей`;
    if (!confirm(`Удалить ${label} из базы? Это не отменяет платёж в ЮKassa.`)) return;

    setDeleting(true);
    setMsg("");
    setError("");
    try {
      if (ids.length === 1) {
        await apiFetch(`/api/admin/payments/subscriptions/${ids[0]}`, { method: "DELETE" });
      } else {
        await apiFetch("/api/admin/payments/subscriptions/bulk-delete", {
          method: "POST",
          body: JSON.stringify({ ids }),
        });
      }
      setMsg(`Удалено записей: ${ids.length}`);
      await load(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить записи");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="admin-page admin-page--payments">
      <header className="admin-page-header">
        <div>
          <h1>Платежи / подписки</h1>
          <p className="admin-page-subtitle">
            Записи подписок в базе. Удаление не отменяет платёж в ЮKassa — только локальную запись.
          </p>
        </div>
        {!loading && (
          <div className="admin-page-meta">
            <span className="admin-count-badge">{items.length}</span>
            <span className="hint">записей</span>
          </div>
        )}
      </header>

      <div className="payments-toolbar card">
        <form className="payments-toolbar-form" onSubmit={onSearch}>
          <label className="payments-search-field">
            <span className="payments-field-label">Поиск</span>
            <input
              placeholder="email, max, статус, сумма, payment id, дата…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="payments-toolbar-actions">
            <button type="submit" className="btn-primary">
              Найти
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setSearch("");
                setQuery("");
              }}
            >
              Сбросить
            </button>
          </div>
        </form>
        {canWrite && someSelected && (
          <div className="payments-bulk-bar">
            <span className="hint">Выбрано: {selected.size}</span>
            <button
              type="button"
              className="btn-secondary btn-danger-outline"
              disabled={deleting}
              onClick={() => void deleteSubscriptions(selectedIds)}
            >
              {deleting ? "Удаление…" : "Удалить выбранные"}
            </button>
          </div>
        )}
      </div>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && items.length === 0 && !error && (
        <div className="card payments-empty">
          <p className="hint">Подписок не найдено</p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="payments-table-wrap">
          <table className="payments-table">
            <thead>
              <tr>
                {canWrite && (
                  <th className="payments-col-check">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      aria-label="Выбрать все"
                      onChange={toggleAll}
                    />
                  </th>
                )}
                <th>Пользователь</th>
                <th>Статус</th>
                <th>Сумма</th>
                <th>Payment ID</th>
                <th>Создан</th>
                {canWrite && <th>Действия</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} className={selected.has(s.id) ? "payments-row--selected" : undefined}>
                  {canWrite && (
                    <td className="payments-col-check">
                      <input
                        type="checkbox"
                        checked={selected.has(s.id)}
                        aria-label={`Выбрать ${s.id}`}
                        onChange={() => toggleOne(s.id)}
                      />
                    </td>
                  )}
                  <td>
                    <Link to={`/users/${s.user_id}`} className="payments-user-link">
                      {contactLabel(s)}
                    </Link>
                  </td>
                  <td>{s.status_label || s.status}</td>
                  <td>{s.amount_rub} ₽</td>
                  <td className="payments-cell-id">{s.yookassa_payment_id || "—"}</td>
                  <td>{formatDate(s.created_at)}</td>
                  {canWrite && (
                    <td className="payments-cell-actions">
                      <button
                        type="button"
                        className="btn-secondary btn-secondary--compact"
                        disabled={syncingUserId === s.user_id}
                        onClick={() => void syncProPayment(s.user_id)}
                      >
                        {syncingUserId === s.user_id ? "…" : "Восстановить Pro"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-secondary--compact btn-danger-outline"
                        disabled={deleting}
                        onClick={() => void deleteSubscriptions([s.id])}
                      >
                        Удалить
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
