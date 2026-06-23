import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBlogNeighbors, resolveBlogMediaUrl } from "../api/blog";

type Props = { slug: string };

export function BlogNeighbors({ slug }: Props) {
  const { data } = useQuery({
    queryKey: ["blog-neighbors", slug],
    queryFn: () => fetchBlogNeighbors(slug),
    staleTime: 5 * 60 * 1000,
  });

  if (!data?.prev && !data?.next) return null;

  return (
    <nav className="blog-neighbors" aria-label="Другие статьи">
      <div className="blog-neighbors__inner">
        {data?.prev ? (
          <Link to={`/blog/${data.prev.slug}`} className="blog-neighbors__item blog-neighbors__item--prev">
            <span className="blog-neighbors__arrow">←</span>
            <span className="blog-neighbors__label">Предыдущая</span>
            <span className="blog-neighbors__name">{data.prev.title}</span>
          </Link>
        ) : <div />}

        {data?.next ? (
          <Link to={`/blog/${data.next.slug}`} className="blog-neighbors__item blog-neighbors__item--next">
            <span className="blog-neighbors__label">Следующая</span>
            <span className="blog-neighbors__name">{data.next.title}</span>
            <span className="blog-neighbors__arrow">→</span>
          </Link>
        ) : <div />}
      </div>
    </nav>
  );
}
