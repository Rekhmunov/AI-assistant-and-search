const API_BASE = import.meta.env.VITE_API_URL || "";

export type BlogCategory = {
  id: string;
  slug: string;
  name: string;
  description: string;
};

export type BlogMedia = {
  id: string;
  url: string;
  width?: number | null;
  height?: number | null;
  alt_text?: string;
};

export type BlogPostListItem = {
  id: string;
  slug: string;
  title: string;
  excerpt: string;
  published_at: string | null;
  reading_time_min: number;
  category: BlogCategory | null;
  cover_image: BlogMedia | null;
};

export type BlogPostPublic = BlogPostListItem & {
  content_html: string;
  updated_at: string;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_title: string;
  og_description: string;
  og_image: BlogMedia | null;
  canonical_path: string;
  robots_index: boolean;
};

function mediaUrl(path: string): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path}`;
}

export function resolveBlogMediaUrl(media: BlogMedia | null | undefined): string {
  if (!media?.url) return "";
  return mediaUrl(media.url);
}

export async function fetchBlogPosts(params?: {
  category?: string;
  offset?: number;
  limit?: number;
}): Promise<BlogPostListItem[]> {
  const qs = new URLSearchParams();
  if (params?.category) qs.set("category", params.category);
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.limit != null) qs.set("limit", String(params.limit));
  const res = await fetch(`${API_BASE}/api/blog/posts?${qs.toString()}`, { credentials: "include" });
  if (!res.ok) throw new Error("Не удалось загрузить статьи");
  const rows = (await res.json()) as BlogPostListItem[];
  return rows.map((row) => ({
    ...row,
    cover_image: row.cover_image
      ? { ...row.cover_image, url: mediaUrl(row.cover_image.url) }
      : null,
  }));
}

export async function fetchBlogCategories(): Promise<BlogCategory[]> {
  const res = await fetch(`${API_BASE}/api/blog/categories`, { credentials: "include" });
  if (!res.ok) throw new Error("Не удалось загрузить категории");
  return res.json();
}

export class BlogPostRedirectError extends Error {
  readonly slug: string;

  constructor(slug: string) {
    super("redirect");
    this.slug = slug;
  }
}

export async function fetchBlogPost(slug: string): Promise<BlogPostPublic> {
  const res = await fetch(`${API_BASE}/api/blog/posts/${encodeURIComponent(slug)}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object" && detail.code === "redirect" && detail.slug) {
      throw new BlogPostRedirectError(String(detail.slug));
    }
    throw new Error("Статья не найдена");
  }
  const post = (await res.json()) as BlogPostPublic;
  return {
    ...post,
    cover_image: post.cover_image ? { ...post.cover_image, url: mediaUrl(post.cover_image.url) } : null,
    og_image: post.og_image ? { ...post.og_image, url: mediaUrl(post.og_image.url) } : null,
  };
}
