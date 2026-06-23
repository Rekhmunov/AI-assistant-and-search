import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { useState } from "react";
import { fetchBlogCategories, fetchBlogPosts, resolveBlogMediaUrl } from "../api/blog";
import { useBlogListMeta } from "../hooks/useBlogMeta";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

export function BlogPage() {
  useBlogListMeta();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search
  const onSearchChange = (val: string) => {
    setSearch(val);
    clearTimeout((window as any)._blogSearchTimer);
    (window as any)._blogSearchTimer = setTimeout(() => setDebouncedSearch(val), 300);
  };

  const { data: posts = [], isLoading } = useQuery({
    queryKey: ["blog-posts", debouncedSearch],
    queryFn: () => fetchBlogPosts({ limit: 50, search: debouncedSearch || undefined }),
  });

  const { data: categories = [] } = useQuery({
    queryKey: ["blog-categories"],
    queryFn: fetchBlogCategories,
  });

  return (
    <div className="blog-layout">
      {/* Боковая панель с категориями */}
      <aside className="blog-sidebar">
        <div className="blog-sidebar-header">
          <span className="blog-sidebar-title">Блог Glosix</span>
        </div>
        <nav className="blog-sidebar-nav" aria-label="Категории">
          <Link
            to="/blog"
            className={`blog-sidebar-item${location.pathname === "/blog" ? " blog-sidebar-item--active" : ""}`}
          >
            <span className="blog-sidebar-item-icon">📋</span>
            <span>Все статьи</span>
            {posts.length > 0 && (
              <span className="blog-sidebar-count">{posts.length}</span>
            )}
          </Link>
          {categories.map((cat) => (
            <Link
              key={cat.id}
              to={`/blog/category/${cat.slug}`}
              className={`blog-sidebar-item${location.pathname === `/blog/category/${cat.slug}` ? " blog-sidebar-item--active" : ""}`}
            >
              <span className="blog-sidebar-item-icon">📁</span>
              <span>{cat.name}</span>
            </Link>
          ))}
        </nav>
      </aside>

      {/* Основной контент */}
      <main className="blog-main">
        <div className="blog-main-header">
          <h1 className="blog-main-title">Все статьи</h1>
          <p className="blog-main-lead">Статьи об умном поиске, ИИ-ассистенте и автоматизации в MAX</p>
        </div>

        {/* Поиск */}
        <div className="blog-search-wrap">
          <div className="blog-search-field">
            <svg className="blog-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              type="search"
              className="blog-search-input"
              placeholder="Поиск по статьям…"
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              aria-label="Поиск по статьям"
            />
            {search && (
              <button
                type="button"
                className="blog-search-clear"
                onClick={() => { setSearch(""); setDebouncedSearch(""); }}
                aria-label="Очистить поиск"
              >
                ×
              </button>
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="blog-loading">
            {[1, 2, 3].map((i) => (
              <div key={i} className="blog-post-row blog-post-row--skeleton" />
            ))}
          </div>
        ) : posts.length === 0 ? (
          <div className="blog-empty">
            {debouncedSearch
              ? <p>По запросу «{debouncedSearch}» ничего не найдено</p>
              : <p>Скоро здесь появятся статьи</p>
            }
          </div>
        ) : (
          <div className="blog-posts-list">
            {posts.map((post) => {
              const cover = resolveBlogMediaUrl(post.cover_image);
              return (
                <article key={post.id} className="blog-post-row">
                  <Link to={`/blog/${post.slug}`} className="blog-post-row-link">
                    <div className="blog-post-row-thumb">
                      {cover ? (
                        <img src={cover} alt="" loading="lazy" />
                      ) : (
                        <div className="blog-post-row-thumb-placeholder">
                          {post.title.charAt(0)}
                        </div>
                      )}
                    </div>
                    <div className="blog-post-row-body">
                      {post.category && (
                        <span className="blog-post-row-cat">{post.category.name}</span>
                      )}
                      <h2 className="blog-post-row-title">{post.title}</h2>
                      {post.excerpt && (
                        <p className="blog-post-row-excerpt">{post.excerpt}</p>
                      )}
                      <div className="blog-post-row-meta">
                        {formatDate(post.published_at)}
                        {post.reading_time_min > 0 && (
                          <span className="blog-post-row-sep">·</span>
                        )}
                        {post.reading_time_min > 0 && (
                          <span>{post.reading_time_min} мин</span>
                        )}
                        {post.view_count > 0 && (
                          <>
                            <span className="blog-post-row-sep">·</span>
                            <span>👁 {post.view_count.toLocaleString("ru-RU")}</span>
                          </>
                        )}
                      </div>
                      {post.tags && post.tags.length > 0 && (
                        <div className="blog-post-row-tags">
                          {post.tags.map((tag) => (
                            <span key={tag} className="blog-post-row-tag">{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  </Link>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
