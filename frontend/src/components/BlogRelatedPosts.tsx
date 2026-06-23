import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBlogRelated, resolveBlogMediaUrl } from "../api/blog";

type Props = { slug: string };

export function BlogRelatedPosts({ slug }: Props) {
  const { data: posts = [] } = useQuery({
    queryKey: ["blog-related", slug],
    queryFn: () => fetchBlogRelated(slug),
    staleTime: 5 * 60 * 1000,
  });

  if (posts.length === 0) return null;

  return (
    <section className="blog-related" aria-label="Читайте также">
      <h2 className="blog-related__title">Читайте также</h2>
      <div className="blog-related__grid">
        {posts.map((p) => {
          const cover = resolveBlogMediaUrl(p.cover_image);
          return (
            <Link key={p.id} to={`/blog/${p.slug}`} className="blog-related__card">
              <div className="blog-related__thumb">
                {cover ? (
                  <img src={cover} alt="" loading="lazy" />
                ) : (
                  <div className="blog-related__thumb-placeholder">{p.title.charAt(0)}</div>
                )}
              </div>
              <div className="blog-related__body">
                {p.category && <span className="blog-related__cat">{p.category.name}</span>}
                <span className="blog-related__name">{p.title}</span>
                {p.reading_time_min > 0 && (
                  <span className="blog-related__meta">{p.reading_time_min} мин чтения</span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
