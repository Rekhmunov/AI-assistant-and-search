import { useEffect } from "react";

const SITE_URL = "https://glosix.ru";

interface LegalMetaOptions {
  title: string;
  publicPath: string;
  metaTitle?: string | null;
  metaDescription?: string | null;
}

/** Устанавливает title, description и canonical для юридических страниц. */
export function useLegalMeta({ title, publicPath, metaTitle, metaDescription }: LegalMetaOptions) {
  useEffect(() => {
    const seoTitle = metaTitle?.trim() || `${title} — Glosix`;
    const seoDescription =
      metaDescription?.trim() ||
      `${title} сервиса Glosix — ИИ-ассистент и умный поиск с источниками.`;
    const canonical = `${SITE_URL}${publicPath.startsWith("/") ? "" : "/"}${publicPath}`;

    document.title = seoTitle;

    const setMeta = (name: string, content: string) => {
      let el = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null;
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute("name", name);
        document.head.appendChild(el);
      }
      el.setAttribute("content", content);
    };

    const setOg = (property: string, content: string) => {
      let el = document.querySelector(`meta[property="${property}"]`) as HTMLMetaElement | null;
      if (!el) {
        el = document.createElement("meta");
        el.setAttribute("property", property);
        document.head.appendChild(el);
      }
      el.setAttribute("content", content);
    };

    const setCanonical = (href: string) => {
      let el = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null;
      if (!el) {
        el = document.createElement("link");
        el.setAttribute("rel", "canonical");
        document.head.appendChild(el);
      }
      el.setAttribute("href", href);
    };

    setMeta("description", seoDescription);
    setOg("og:title", seoTitle);
    setOg("og:description", seoDescription);
    setOg("og:url", canonical);
    setOg("og:type", "website");
    setMeta("twitter:title", seoTitle);
    setMeta("twitter:description", seoDescription);
    setCanonical(canonical);

    return () => {
      // Сбрасываем до дефолтов при уходе со страницы
      document.title = "Glosix - умный поиск с источниками, ИИ чат";
    };
  }, [title, publicPath, metaTitle, metaDescription]);
}
