import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  BlogPostRedirectError,
  fetchBlogPost,
  fetchBlogCategories,
  resolveBlogMediaUrl,
} from "../api/blog";
import { BlogComments } from "../components/BlogComments";
import { BlogTrySearch } from "../components/BlogTrySearch";
import { BlogToC } from "../components/BlogToC";
import { BlogShareButtons } from "../components/BlogShareButtons";
import { BlogRelatedPosts } from "../components/BlogRelatedPosts";
import { BlogNeighbors } from "../components/BlogNeighbors";
import { BlogHelpfulWidget } from "../components/BlogHelpfulWidget";
import { ReadingProgressBar } from "../components/ReadingProgressBar";
import { useBlogPostMeta } from "../hooks/useBlogMeta";

const API_BASE = import.meta.env.VITE_API_URL || "";
const PUBLIC_SITE = import.meta.env.VITE_PUBLIC_URL || "https://glosix.ru";

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

function incrementViewCount(slug: string) {
  fetch(`${API_BASE}/api/blog/posts/${slug}/view`, { method: "POST" }).catch(() => {});
}

export function BlogPostPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  // processedHtml holds content_html with injected heading ids for ToC anchors
  const [processedHtml, setProcessedHtml] = useState<string | null>(null);

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

  const { data: categories = [] } = useQuery({
    queryKey: ["blog-categories"],
    queryFn: fetchBlogCategories,
  });

  useBlogPostMeta(post ?? null);

  useEffect(() => {
    if (slug) incrementViewCount(slug);
  }, [slug]);

  // Reset processedHtml when slug changes
  useEffect(() => { setProcessedHtml(null); }, [slug]);

  const onTocProcessed = useCallback((html: string) => {
    setProcessedHtml(html);
  }, []);

  const cover = post ? resolveBlogMediaUrl(post.cover_image) : null;
  const pageUrl = post ? `${PUBLIC_SITE}/blog/${post.slug}` : "";
  const displayHtml = processedHtml ?? post?.content_html ?? "";

  return (
    <div className="blog-layout">
      {/* Reading progress bar */}
      <ReadingProgressBar />

      {/* Боковая панель */}
      <aside className="blog-sidebar">
        <div className="blog-sidebar-header">
          <Link to="/blog" className="blog-sidebar-title">Блог Glosix</Link>
        </div>
        <nav className="blog-sidebar-nav" aria-label="Категории">
          <Link to="/blog" className="blog-sidebar-item">
            <span className="blog-sidebar-item-icon">📋</span>
            <span>Все статьи</span>
          </Link>
          {categories.map((cat) => (
            <Link
              key={cat.id}
              to={`/blog/category/${cat.slug}`}
              className={`blog-sidebar-item${
                post?.category?.slug === cat.slug ? " blog-sidebar-item--active" : ""
              }${location.pathname === `/blog/category/${cat.slug}` ? " blog-sidebar-item--active" : ""}`}
            >
              <span className="blog-sidebar-item-icon">📁</span>
              <span>{cat.name}</span>
            </Link>
          ))}
        </nav>
      </aside>

      {/* Контент статьи */}
      <main className="blog-post-main">
        {isLoading ? (
          <div className="blog-post-loading">
            <div className="blog-post-skeleton blog-post-skeleton--title" />
            <div className="blog-post-skeleton blog-post-skeleton--meta" />
            <div className="blog-post-skeleton blog-post-skeleton--body" />
          </div>
        ) : error || !post ? (
          <div className="blog-post-error">
            <p>Статья не найдена.</p>
            <Link to="/blog" className="blog-post-back">← Все статьи</Link>
          </div>
        ) : (
          <article>
            {/* Хлебные крошки */}
            <nav className="blog-breadcrumbs-inline" aria-label="Навигация">
              <Link to="/blog">Блог</Link>
              {post.category && (
                <>
                  <span aria-hidden> / </span>
                  <Link to={`/blog/category/${post.category.slug}`}>{post.category.name}</Link>
                </>
              )}
              <span aria-hidden> / </span>
              <span className="blog-breadcrumb-current">{post.title}</span>
            </nav>

            {/* Заголовок */}
            <header className="blog-article-header">
              {post.category && (
                <Link to={`/blog/category/${post.category.slug}`} className="blog-article-cat">
                  {post.category.name}
                </Link>
              )}
              <h1 className="blog-article-title">{post.title}</h1>
              <div className="blog-article-meta">
                <span>{formatDate(post.published_at)}</span>
                {post.author_name && <span className="blog-meta-sep">·</span>}
                {post.author_name && <span>{post.author_name}</span>}
                {post.reading_time_min > 0 && <span className="blog-meta-sep">·</span>}
                {post.reading_time_min > 0 && <span>{post.reading_time_min} мин чтения</span>}
                <span className="blog-meta-sep">·</span>
                <span className="blog-meta-views">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                  {post.view_count.toLocaleString("ru-RU")}
                </span>
              </div>
              {/* Теги */}
              {post.tags && post.tags.length > 0 && (
                <div className="blog-article-tags">
                  {post.tags.map((tag) => (
                    <span key={tag} className="blog-article-tag">{tag}</span>
                  ))}
                </div>
              )}
            </header>

            {/* Обложка */}
            {cover && (
              <img src={cover} alt="" className="blog-article-cover" loading="lazy" />
            )}

            {/* Оглавление */}
            {post.content_html && (
              <BlogToC contentHtml={post.content_html} onProcessed={onTocProcessed} />
            )}

            {/* Контент */}
            <div
              className="blog-article-content prose"
              dangerouslySetInnerHTML={{ __html: displayHtml }}
            />

            {/* Поделиться */}
            <BlogShareButtons title={post.title} url={pageUrl} />

            {/* Была ли статья полезна */}
            <BlogHelpfulWidget
              slug={post.slug}
              helpfulYes={post.helpful_yes || 0}
              helpfulNo={post.helpful_no || 0}
            />

            {/* Навигация пред/след */}
            <BlogNeighbors slug={post.slug} />

            {/* Комментарии */}
            {post.comments_enabled && <BlogComments slug={post.slug} />}

            {/* CTA */}
            <BlogTrySearch />

            {/* Похожие статьи */}
            <BlogRelatedPosts slug={post.slug} />

            {/* Подвал */}
            <footer className="blog-article-footer">
              <Link to="/blog" className="blog-article-back">
                ← Все статьи
              </Link>
              <Link to="/" className="btn-primary">
                Попробовать Glosix
              </Link>
            </footer>
          </article>
        )}
      </main>
    </div>
  );
}
