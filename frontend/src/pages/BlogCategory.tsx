import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchBlogCategories, fetchBlogPosts, resolveBlogMediaUrl } from "../api/blog";
import { useBlogListMeta } from "../hooks/useBlogMeta";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  } catch {
    return "";
  }
}

export function BlogCategoryPage() {
  const { slug = "" } = useParams();
  const { data: categories = [] } = useQuery({
    queryKey: ["blog-categories"],
    queryFn: fetchBlogCategories,
  });
  const category = categories.find((c) => c.slug === slug);
  useBlogListMeta({
    categorySlug: slug,
    categoryName: category?.name,
    categoryDescription: category?.description ?? undefined,
  });
  const { data: posts = [], isLoading } = useQuery({
    queryKey: ["blog-posts", slug],
    queryFn: () => fetchBlogPosts({ category: slug, limit: 50 }),
    enabled: Boolean(slug),
  });

  return (
    <div className="page page-blog">
      <header className="blog-header">
        <nav className="blog-breadcrumbs">
          <Link to="/blog">Блог</Link>
          <span aria-hidden> / </span>
          <span>{category?.name ?? slug}</span>
        </nav>
        <h1 className="blog-title">{category?.name ?? "Категория"}</h1>
        {category?.description && <p className="blog-lead">{category.description}</p>}
      </header>
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
                    <h2 className="blog-card-title">{post.title}</h2>
                    {post.excerpt && <p className="blog-card-excerpt">{post.excerpt}</p>}
                    <footer className="blog-card-meta">{formatDate(post.published_at)}</footer>
                  </div>
                </Link>
              </article>
            );
          })}
        </div>
      )}
      {!isLoading && posts.length === 0 && <p className="blog-muted">В этой категории пока нет статей.</p>}
    </div>
  );
}
