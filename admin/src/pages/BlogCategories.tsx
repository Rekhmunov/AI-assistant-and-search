import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type Category = {
  id: string;
  slug: string;
  name: string;
  description: string;
};

export function BlogCategoriesPage() {
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [items, setItems] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<Category[]>("/api/admin/blog/categories");
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить категории");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setMsg("");
    setError("");
    try {
      await apiFetch("/api/admin/blog/categories", {
        method: "POST",
        body: JSON.stringify({ name, slug: slug.trim() || undefined, description: "" }),
      });
      setName("");
      setSlug("");
      setMsg("Категория создана");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    }
  };

  const remove = async (cat: Category) => {
    if (!window.confirm(`Удалить категорию «${cat.name}»?`)) return;
    setMsg("");
    setError("");
    try {
      await apiFetch(`/api/admin/blog/categories/${cat.id}`, { method: "DELETE" });
      setMsg("Категория удалена");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить");
    }
  };

  return (
    <div className="admin-page admin-page--blog-categories">
      <header className="admin-page-header">
        <div>
          <h1>Категории блога</h1>
          <p className="admin-page-subtitle">Группировка статей в публичном разделе /blog.</p>
        </div>
        <div className="admin-page-meta">
          {!loading && <span className="admin-count-badge">{items.length}</span>}
          {!loading && <span className="hint">категорий</span>}
        </div>
      </header>

      <div className="blog-edit-header-actions blog-categories-nav">
        <Link to="/blog" className="btn-secondary">
          ← К статьям
        </Link>
      </div>

      {canWrite && (
        <section className="card blog-cat-create">
          <h2 className="blog-section-title">Новая категория</h2>
          <form className="blog-cat-form" onSubmit={create}>
            <label className="blog-field">
              <span className="blog-field-label">Название</span>
              <input
                placeholder="Например: Продукт"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="blog-field">
              <span className="blog-field-label">Slug (опционально)</span>
              <input
                placeholder="produkt"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
              />
            </label>
            <div className="blog-cat-form-actions">
              <button type="submit" className="btn-primary">
                Добавить
              </button>
            </div>
          </form>
        </section>
      )}

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && items.length === 0 && !error && (
        <div className="card blog-empty">
          <p className="blog-empty-title">Категорий пока нет</p>
          <p className="hint">Создайте первую категорию выше.</p>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="blog-table-wrap admin-table-wrap">
          <table className="blog-table blog-cat-table admin-responsive-table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Slug</th>
                <th>Описание</th>
                {canWrite && <th aria-label="Действия" />}
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td data-label="Название">
                    <strong>{c.name}</strong>
                  </td>
                  <td data-label="Slug">
                    <code>{c.slug}</code>
                  </td>
                  <td data-label="Описание" className="blog-cat-desc">
                    {c.description || "—"}
                  </td>
                  {canWrite && (
                    <td className="admin-table-action-cell" data-label="">
                      <button
                        type="button"
                        className="btn-secondary btn-secondary--compact btn-danger-outline"
                        onClick={() => void remove(c)}
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
