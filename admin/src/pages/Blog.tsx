import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

const API = import.meta.env.VITE_API_URL || "";
const PUBLIC_SITE = import.meta.env.VITE_PUBLIC_URL || "https://glosix.ru";

type BlogPostItem = {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  status: string;
  published_at: string | null;
  reading_time_min: number;
  view_count?: number;
  category: { name: string } | null;
  cover_image?: { url: string } | null;
  updated_at?: string;
};

type ListResponse = { items: BlogPostItem[]; total: number };

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  published: "Опубликовано",
  archived: "Архив",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function mediaSrc(url: string | undefined): string {
  if (!url) return "";
  return url.startsWith("http") ? url : `${API}${url}`;
}

function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? status;
  return <span className={`blog-status-badge blog-status-badge--${status}`}>{label}</span>;
}

export function BlogPage() {
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [items, setItems] = useState<BlogPostItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [rebuildBusy, setRebuildBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (search.trim()) params.set("search", search.trim());
      const data = await apiFetch<ListResponse>(`/api/admin/blog/posts?${params.toString()}`);
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить статьи");
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [status]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    void load();
  };

  const remove = async (id: string, title: string) => {
    if (!window.confirm(`Удалить «${title}»?`)) return;
    setMsg("");
    try {
      await apiFetch(`/api/admin/blog/posts/${id}`, { method: "DELETE" });
      setMsg("Статья удалена");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить");
    }
  };

  const rebuildPrerender = async () => {
    setRebuildBusy(true);
    setMsg("");
    setError("");
    try {
      await apiFetch("/api/admin/blog/rebuild-prerender", { method: "POST" });
      setMsg("HTML prerender обновлён");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка prerender");
    } finally {
      setRebuildBusy(false);
    }
  };

  return (
    <div className="admin-page admin-page--blog">
      <header className="admin-page-header">
        <div>
          <h1>Блог</h1>
        </div>
        <div className="admin-page-meta">
          {!loading && <span className="admin-count-badge">{total}</span>}
          {!loading && <span className="hint">статей</span>}
        </div>
      </header>

      <div className="blog-toolbar card">
        <form className="blog-toolbar-form" onSubmit={onSearch}>
          <div className="blog-toolbar-top">
            <label className="blog-field blog-field--search">
              <span className="blog-field-label">Поиск</span>
              <input
                placeholder="Заголовок или slug"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label className="blog-field blog-field--status">
              <span className="blog-field-label">Статус</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Все</option>
                <option value="draft">Черновики</option>
                <option value="published">Опубликованные</option>
                <option value="archived">Архив</option>
              </select>
            </label>
            <button type="submit" className="btn-primary" style={{ alignSelf: "flex-end" }}>
              Найти
            </button>
            <button type="button" className="btn-secondary" style={{ alignSelf: "flex-end" }} onClick={() => void load()}>
              Обновить
            </button>
          </div>
          <div className="blog-toolbar-actions">
            <Link to="/blog/categories" className="btn-secondary">
              Категории
            </Link>
            {canWrite && (
              <>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={rebuildBusy}
                  onClick={() => void rebuildPrerender()}
                >
                  {rebuildBusy ? "Prerender…" : "Обновить prerender"}
                </button>
                <Link to="/blog/new" className="btn-primary">
                  + Новая статья
                </Link>
              </>
            )}
          </div>
        </form>
      </div>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}
      {loading && <p className="hint">Загрузка…</p>}

      {!loading && items.length === 0 && !error && (
        <div className="card blog-empty">
          <p className="blog-empty-title">Статей пока нет</p>
          <p className="hint">Создайте первую публикацию или измените фильтры.</p>
          {canWrite && (
            <Link to="/blog/new" className="btn-primary">
              Новая статья
            </Link>
          )}
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="blog-table-wrap admin-table-wrap">
          <table className="blog-table admin-responsive-table">
            <thead>
              <tr>
                <th>Статья</th>
                <th>Статус</th>
                <th>Категория</th>
                <th>👁</th>
                <th>Время чтения</th>
                <th>Опубликовано</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {items.map((post) => {
                const cover = mediaSrc(post.cover_image?.url);
                const publicUrl = `${PUBLIC_SITE}/blog/${post.slug}`;
                return (
                  <tr key={post.id}>
                    <td data-label="Статья">
                      <div className="blog-post-cell">
                        <div className="blog-post-thumb" aria-hidden>
                          {cover ? (
                            <img src={cover} alt="" />
                          ) : (
                            <span className="blog-post-thumb-fallback">{post.title.charAt(0) || "?"}</span>
                          )}
                        </div>
                        <div className="blog-post-meta">
                          <Link className="blog-post-title" to={`/blog/${post.id}`}>
                            {post.title}
                          </Link>
                          <span className="blog-post-slug">
                            <code>{post.slug}</code>
                          </span>
                          {post.excerpt && <span className="blog-post-excerpt">{post.excerpt}</span>}
                          {post.status === "published" && (
                            <a className="blog-post-public-link" href={publicUrl} target="_blank" rel="noreferrer">
                              Открыть на сайте ↗
                            </a>
                          )}
                        </div>
                      </div>
                    </td>
                    <td data-label="Статус">
                      <StatusBadge status={post.status} />
                    </td>
                    <td data-label="Категория">{post.category?.name ?? "—"}</td>
                    <td data-label="👁" className="blog-views-cell">
                      {(post.view_count ?? 0).toLocaleString("ru-RU")}
                    </td>
                    <td data-label="Время чтения">{post.reading_time_min} мин</td>
                    <td data-label="Опубликовано">{formatDate(post.published_at)}</td>
                    <td className="admin-table-action-cell" data-label="">
                      <div className="blog-row-actions">
                        <Link className="btn-secondary btn-secondary--compact" to={`/blog/${post.id}`}>
                          Редактировать
                        </Link>
                        {canWrite && (
                          <button
                            type="button"
                            className="btn-secondary btn-secondary--compact btn-danger-outline"
                            onClick={() => void remove(post.id, post.title)}
                          >
                            Удалить
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
