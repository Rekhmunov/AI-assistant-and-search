import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type BlogPostItem = {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  status: string;
  published_at: string | null;
  reading_time_min: number;
  category: { name: string } | null;
  updated_at?: string;
};

type ListResponse = { items: BlogPostItem[]; total: number };

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU");
  } catch {
    return iso;
  }
}

export function BlogPage() {
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [items, setItems] = useState<BlogPostItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (search.trim()) params.set("search", search.trim());
      const data = await apiFetch<ListResponse>(`/api/admin/blog/posts?${params.toString()}`);
      setItems(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [status]);

  const remove = async (id: string, title: string) => {
    if (!window.confirm(`Удалить «${title}»?`)) return;
    await apiFetch(`/api/admin/blog/posts/${id}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="page">
      <div className="page-header-row">
        <h1>Блог</h1>
        {canWrite && (
          <Link to="/blog/new" className="btn-primary">
            Новая статья
          </Link>
        )}
      </div>
      <div className="blog-filters">
        <select className="field-input" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Все статусы</option>
          <option value="draft">Черновики</option>
          <option value="published">Опубликованные</option>
          <option value="archived">Архив</option>
        </select>
        <input
          className="field-input"
          placeholder="Поиск по заголовку"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
        />
        <button type="button" className="btn-secondary" onClick={() => load()}>
          Найти
        </button>
        <Link to="/blog/categories" className="btn-secondary">
          Категории
        </Link>
        {canWrite && (
          <button
            type="button"
            className="btn-secondary"
            onClick={async () => {
              await apiFetch("/api/admin/blog/rebuild-prerender", { method: "POST" });
              alert("Prerender обновлён");
            }}
          >
            Обновить prerender
          </button>
        )}
      </div>
      {loading ? (
        <p>Загрузка…</p>
      ) : (
        <>
          <p className="muted">Всего: {total}</p>
          <table className="data-table">
            <thead>
              <tr>
                <th>Заголовок</th>
                <th>Slug</th>
                <th>Статус</th>
                <th>Категория</th>
                <th>Опубликовано</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((post) => (
                <tr key={post.id}>
                  <td>
                    <Link to={`/blog/${post.id}`}>{post.title}</Link>
                  </td>
                  <td>
                    <code>{post.slug}</code>
                  </td>
                  <td>{post.status}</td>
                  <td>{post.category?.name ?? "—"}</td>
                  <td>{formatDate(post.published_at)}</td>
                  <td className="table-actions">
                    <Link to={`/blog/${post.id}`} className="btn-link">
                      Редактировать
                    </Link>
                    {canWrite && (
                      <button type="button" className="btn-link btn-link--danger" onClick={() => remove(post.id, post.title)}>
                        Удалить
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <p className="muted">Статей пока нет</p>}
        </>
      )}
    </div>
  );
}
