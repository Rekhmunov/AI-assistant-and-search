import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  BlogPostRedirectError,
  fetchBlogPost,
  resolveBlogMediaUrl,
} from "../api/blog";
import { useBlogPostMeta } from "../hooks/useBlogMeta";

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

export function BlogPostPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();

  const { data: post, isLoading, error } = useQuery({
    queryKey: ["blog-post", slug],
    queryFn: async () => {
      try {
        return await fetchBlogPost(slug);
      } catch (e) {
        if (e instanceof BlogPostRedirectError) {
          navigate(`/blog/${e.slug}`, { replace: true });
          return null;
        }
        throw e;
      }
    },
    enabled: Boolean(slug),
  });

  useBlogPostMeta(post ?? null);

  if (isLoading) {
    return (
      <div className="page page-blog-post">
        <p className="blog-muted">Загрузка…</p>
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="page page-blog-post">
        <p className="blog-muted">Статья не найдена.</p>
        <Link to="/blog">← К блогу</Link>
      </div>
    );
  }

  const cover = resolveBlogMediaUrl(post.cover_image);

  return (
    <article className="page page-blog-post">
      <nav className="blog-breadcrumbs">
        <Link to="/">Glosix</Link>
        <span aria-hidden> / </span>
        <Link to="/blog">Блог</Link>
        {post.category && (
          <>
            <span aria-hidden> / </span>
            <Link to={`/blog/category/${post.category.slug}`}>{post.category.name}</Link>
          </>
        )}
      </nav>
      <header className="blog-post-header">
        {post.category && <span className="blog-post-cat">{post.category.name}</span>}
        <h1 className="blog-post-title">{post.title}</h1>
        <p className="blog-post-meta">
          {formatDate(post.published_at)}
          {post.reading_time_min > 0 && ` · ${post.reading_time_min} мин чтения`}
        </p>
      </header>
      {cover && <img src={cover} alt="" className="blog-post-cover" />}
      <div
        className="blog-post-content prose"
        dangerouslySetInnerHTML={{ __html: post.content_html }}
      />
      <footer className="blog-post-footer">
        <Link to="/blog" className="btn-secondary">
          ← Все статьи
        </Link>
        <Link to="/" className="btn-primary">
          Попробовать Glosix
        </Link>
      </footer>
    </article>
  );
}
