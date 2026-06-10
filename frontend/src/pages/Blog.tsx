import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
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
  const { data: posts = [], isLoading } = useQuery({
    queryKey: ["blog-posts"],
    queryFn: () => fetchBlogPosts({ limit: 50 }),
  });
  const { data: categories = [] } = useQuery({
    queryKey: ["blog-categories"],
    queryFn: fetchBlogCategories,
  });

  return (
    <div className="page page-blog">
      <header className="blog-header">
        <h1 className="blog-title">Блог Glosix</h1>
        <p className="blog-lead">Статьи об умном поиске, ИИ-ассистенте и автоматизации в MAX</p>
      </header>
      {categories.length > 0 && (
        <nav className="blog-categories" aria-label="Категории">
          <Link to="/blog" className="blog-cat-chip blog-cat-chip--active">
            Все
          </Link>
          {categories.map((cat) => (
            <Link key={cat.id} to={`/blog/category/${cat.slug}`} className="blog-cat-chip">
              {cat.name}
            </Link>
          ))}
        </nav>
      )}
      {isLoading ? (
        <p className="blog-muted">Загрузка…</p>
      ) : (
        <div className="blog-grid">
          {posts.map((post) => {
            const cover = resolveBlogMediaUrl(post.cover_image);
            return (
              <article key={post.id} className="blog-card">
                <Link to={`/blog/${post.slug}`} className="blog-card-link">
                  {cover ? (
                    <img src={cover} alt="" className="blog-card-cover" loading="lazy" />
                  ) : (
                    <div className="blog-card-cover blog-card-cover--placeholder" />
                  )}
                  <div className="blog-card-body">
                    {post.category && <span className="blog-card-cat">{post.category.name}</span>}
                    <h2 className="blog-card-title">{post.title}</h2>
                    {post.excerpt && <p className="blog-card-excerpt">{post.excerpt}</p>}
                    <footer className="blog-card-meta">
                      {formatDate(post.published_at)}
                      {post.reading_time_min > 0 && ` · ${post.reading_time_min} мин`}
                    </footer>
                  </div>
                </Link>
              </article>
            );
          })}
        </div>
      )}
      {!isLoading && posts.length === 0 && <p className="blog-muted">Скоро здесь появятся статьи.</p>}
    </div>
  );
}
