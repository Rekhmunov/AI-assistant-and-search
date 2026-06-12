import { useEffect } from "react";
import type { BlogPostPublic } from "../api/blog";
import { resolveBlogMediaUrl } from "../api/blog";

const SITE = "https://glosix.ru";

function upsertMeta(attr: "name" | "property", key: string, content: string) {
  const selector = `meta[${attr}="${key}"]`;
  let el = document.querySelector(selector) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel: string, href: string) {
  let el = document.querySelector(`link[rel="${rel}"]`) as HTMLLinkElement | null;
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function removeBlogMeta() {
  [
    'meta[name="description"]',
    'meta[name="keywords"]',
    'meta[property="og:title"]',
    'meta[property="og:description"]',
    'meta[property="og:url"]',
    'meta[property="og:image"]',
    'meta[property="og:type"]',
    'meta[name="twitter:card"]',
    'meta[name="twitter:title"]',
    'meta[name="twitter:description"]',
    'meta[name="twitter:image"]',
    'link[rel="canonical"]',
    'script[data-blog-jsonld="1"]',
  ].forEach((sel) => document.querySelector(sel)?.remove());
}

export function useBlogListMeta(options?: { categorySlug?: string; categoryName?: string; categoryDescription?: string }) {
  const { categorySlug, categoryName, categoryDescription } = options ?? {};
  useEffect(() => {
    if (categorySlug && categoryName) {
      // Страница категории
      const canonical = `${SITE}/blog/category/${categorySlug}`;
      document.title = `${categoryName} — Блог Glosix`;
      upsertMeta("name", "description", categoryDescription || `Статьи в категории «${categoryName}» — блог Glosix об умном поиске и ИИ-ассистенте.`);
      upsertLink("canonical", canonical);
      upsertMeta("property", "og:title", `${categoryName} — Блог Glosix`);
      upsertMeta("property", "og:url", canonical);
      upsertMeta("property", "og:type", "website");
    } else {
      // Страница списка всех статей
      document.title = "Блог Glosix — статьи об ИИ-поиске и ассистентах";
      upsertMeta("name", "description", "Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды.");
      upsertLink("canonical", `${SITE}/blog`);
      upsertMeta("property", "og:title", "Блог Glosix — статьи об ИИ-поиске и ассистентах");
      upsertMeta("property", "og:description", "Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды.");
      upsertMeta("property", "og:url", `${SITE}/blog`);
      upsertMeta("property", "og:type", "website");
    }
    return () => removeBlogMeta();
  }, [categorySlug, categoryName, categoryDescription]);
}

export function useBlogPostMeta(post: BlogPostPublic | null) {
  useEffect(() => {
    if (!post) return;
    const title = post.meta_title || post.title;
    const description = post.meta_description || post.excerpt;
    const ogTitle = post.og_title || title;
    const ogDesc = post.og_description || description;
    const canonical = `${SITE}${post.canonical_path}`;
    const ogImage = resolveBlogMediaUrl(post.og_image || post.cover_image);

    document.title = `${title} — Glosix`;
    upsertMeta("name", "description", description);
    if (post.meta_keywords) upsertMeta("name", "keywords", post.meta_keywords);
    upsertLink("canonical", canonical);
    upsertMeta("property", "og:title", ogTitle);
    upsertMeta("property", "og:description", ogDesc);
    upsertMeta("property", "og:url", canonical);
    upsertMeta("property", "og:type", "article");
    if (ogImage) upsertMeta("property", "og:image", ogImage);
    upsertMeta("name", "twitter:card", "summary_large_image");
    upsertMeta("name", "twitter:title", ogTitle);
    upsertMeta("name", "twitter:description", ogDesc);
    if (ogImage) upsertMeta("name", "twitter:image", ogImage);

    if (post.robots_index) {
      document.querySelector('meta[name="robots"]')?.remove();
    } else {
      upsertMeta("name", "robots", "noindex, nofollow");
    }

    const jsonLd = {
      "@context": "https://schema.org",
      "@type": "BlogPosting",
      headline: post.title,
      description: description,
      datePublished: post.published_at,
      dateModified: post.updated_at,
      mainEntityOfPage: canonical,
      image: ogImage ? [ogImage] : undefined,
      author: post.author_name
        ? { "@type": "Person", name: post.author_name }
        : { "@type": "Organization", name: "Glosix", url: SITE },
      publisher: { "@type": "Organization", name: "Glosix", url: SITE },
    };
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.setAttribute("data-blog-jsonld", "1");
    script.textContent = JSON.stringify(jsonLd);
    document.head.appendChild(script);

    return () => removeBlogMeta();
  }, [post]);
}
