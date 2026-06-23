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
  view_count: number;
  helpful_yes: number;
  helpful_no: number;
  tags: string[];
  category: { name: string } | null;
  cover_image?: { url: string } | null;
  updated_at?: string;
};

type ListResponse = { items: BlogPostItem[]; total: number };

const STATUS_LABELS: Record<string, string> = {
  draft: "Черновик",
  scheduled: "Запланировано",
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

function formatShortDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
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

function HelpfulBar({ yes, no }: { yes: number; no: number }) {
  const total = yes + no;
  if (total === 0) return <span className="blog-helpful-empty">—</span>;
  const pct = Math.round((yes / total) * 100);
  return (
    <div className="blog-helpful-bar">
      <div className="blog-helpful-bar-fill" style={{ width: `${pct}%` }} title={`${pct}%`} />
      <span className="blog-helpful-bar-label">
        👍{yes} / 👎{no}
      </span>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
  accent,
}: {
  icon: string;
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className={`blog-stat-card${accent ? " blog-stat-card--accent" : ""}`}>
      <span className="blog-stat-icon">{icon}</span>
      <span className="blog-stat-value">{typeof value === "number" ? value.toLocaleString("ru-RU") : value}</span>
      <span className="blog-stat-label">{label}</span>
      {sub && <span className="blog-stat-sub">{sub}</span>}
    </div>
  );
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

  // Load ALL posts (no filter) for dashboard
  const [allItems, setAllItems] = useState<BlogPostItem[]>([]);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (status) params.set("status", status);
      if (search.trim()) params.set("search", search.trim());
      const data = await apiFetch<ListResponse>(`/api/admin/blog/posts?${params.toString()}`);
      setItems(data.items);
      setTotal(data.total);
      // Update allItems only when no filter active (for dashboard accuracy)
      if (!status && !search.trim()) setAllItems(data.items);
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

  // Dashboard stats (from allItems — all posts)
  const published = allItems.filter((p) => p.status === "published");
  const totalViews = allItems.reduce((s, p) => s + (p.view_count || 0), 0);
  const totalYes = allItems.reduce((s, p) => s + (p.helpful_yes || 0), 0);
  const totalNo = allItems.reduce((s, p) => s + (p.helpful_no || 0), 0);
  const totalVotes = totalYes + totalNo;
  const helpfulPct = totalVotes > 0 ? Math.round((totalYes / totalVotes) * 100) : null;
  const topByViews = [...allItems].sort((a, b) => (b.view_count || 0) - (a.view_count || 0))[0];
  const avgReading =
    published.length > 0
      ? Math.round(published.reduce((s, p) => s + p.reading_time_min, 0) / published.length)
      : 0;

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

      {/* ── Dashboard ── */}
      {!loading && allItems.length > 0 && (
        <div className="blog-dashboard">
          <div className="blog-stat-grid">
            <StatCard icon="📝" label="Опубликовано" value={published.length} sub={`из ${allItems.length} всего`} />
            <StatCard icon="👁" label="Просмотров всего" value={totalViews} accent />
            <StatCard
              icon="👍"
              label="Полезных статей"
              value={helpfulPct !== null ? `${helpfulPct}%` : "—"}
              sub={totalVotes > 0 ? `${totalYes} да / ${totalNo} нет` : "нет голосов"}
            />
            <StatCard icon="⏱" label="Среднее время чтения" value={avgReading > 0 ? `${avgReading} мин` : "—"} />
          </div>
          {topByViews && topByViews.view_count > 0 && (
            <div className="blog-top-post">
              <span className="blog-top-post-label">🏆 Топ по просмотрам:</span>
              <Link to={`/blog/${topByViews.id}`} className="blog-top-post-link">
                {topByViews.title}
              </Link>
              <span className="blog-top-post-views">{topByViews.view_count.toLocaleString("ru-RU")} просмотров</span>
              {topByViews.status === "published" && (
                <a
                  href={`${PUBLIC_SITE}/blog/${topByViews.slug}`}
                  target="_blank"
                  rel="noreferrer"
                  className="blog-top-post-ext"
                >
                  ↗
                </a>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Toolbar ── */}
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
                <option value="scheduled">Запланированные</option>
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
                <th>👁 Просмотры</th>
                <th>👍 / 👎</th>
                <th>Теги</th>
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
                      <span className="blog-views-num">{(post.view_count ?? 0).toLocaleString("ru-RU")}</span>
                    </td>
                    <td data-label="👍/👎" className="blog-helpful-cell">
                      <HelpfulBar yes={post.helpful_yes || 0} no={post.helpful_no || 0} />
                    </td>
                    <td data-label="Теги">
                      {post.tags && post.tags.length > 0 ? (
                        <div className="blog-tags-cell">
                          {post.tags.slice(0, 3).map((t) => (
                            <span key={t} className="blog-tag-pill">{t}</span>
                          ))}
                          {post.tags.length > 3 && (
                            <span className="blog-tag-pill blog-tag-pill--more">+{post.tags.length - 3}</span>
                          )}
                        </div>
                      ) : (
                        <span className="hint">—</span>
                      )}
                    </td>
                    <td data-label="Опубликовано">{formatShortDate(post.published_at)}</td>
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
