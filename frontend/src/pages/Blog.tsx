import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
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

  const { data: posts = [], isLoading } = useQuery({
    queryKey: ["blog-posts"],
    queryFn: () => fetchBlogPosts({ limit: 50 }),
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

        {isLoading ? (
          <div className="blog-loading">
            {[1, 2, 3].map((i) => (
              <div key={i} className="blog-post-row blog-post-row--skeleton" />
            ))}
          </div>
        ) : posts.length === 0 ? (
          <div className="blog-empty">
            <p>Скоро здесь появятся статьи</p>
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
                        {(post as any).view_count > 0 && (
                          <>
                            <span className="blog-post-row-sep">·</span>
                            <span>👁 {((post as any).view_count as number).toLocaleString("ru-RU")}</span>
                          </>
                        )}
                      </div>
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
