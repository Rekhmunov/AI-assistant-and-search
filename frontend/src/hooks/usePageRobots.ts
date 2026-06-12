import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { hasMaxWebAppHashInUrl, isMaxWebApp } from "../lib/maxApp";
import { shouldNoindexPage } from "../lib/pageRobots";

const DEFAULT_TITLE = "Glosix - умный поиск с источниками, ИИ чат";
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive";
const SITE_URL = "https://glosix.ru";
const SITE_IMAGE = "https://glosix.ru/og-image.png";

const HOME_JSON_LD = JSON.stringify({
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "Glosix",
  "url": SITE_URL,
  "description": "ИИ-ассистент и умный поиск с источниками. Находит актуальную информацию в интернете и даёт готовый ответ.",
  "potentialAction": {
    "@type": "SearchAction",
    "target": {
      "@type": "EntryPoint",
      "urlTemplate": `${SITE_URL}/?q={search_term_string}`,
    },
    "query-input": "required name=search_term_string",
  },
});

function ensureMeta(name: string, content: string): HTMLMetaElement {
  let el = document.querySelector(`meta[name="${name}"]`) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("name", name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
  return el;
}

function ensureOg(property: string, content: string) {
  let el = document.querySelector(`meta[property="${property}"]`) as HTMLMetaElement | null;
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("property", property);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function removeMeta(name: string) {
  document.querySelector(`meta[name="${name}"]`)?.remove();
}

function removeCanonical() {
  document.querySelector('link[rel="canonical"]')?.remove();
}

function removePublicSeoMeta() {
  document.querySelector('meta[name="description"]')?.remove();
  document.querySelectorAll('meta[property^="og:"], meta[name^="twitter:"]').forEach((el) => {
    el.remove();
  });
}

function ensureHomeJsonLd() {
  const id = "jsonld-website";
  if (document.getElementById(id)) return;
  const script = document.createElement("script");
  script.id = id;
  script.type = "application/ld+json";
  script.textContent = HOME_JSON_LD;
  document.head.appendChild(script);
}

function removeHomeJsonLd() {
  document.getElementById("jsonld-website")?.remove();
}

/** Управляет robots-мета, JSON-LD и og-тегами для каждого маршрута. */
export function usePageRobots() {
  const { pathname, search, hash } = useLocation();

  useEffect(() => {
    const isPrivate =
      shouldNoindexPage(pathname, search, hash) || isMaxWebApp() || hasMaxWebAppHashInUrl();
    if (isPrivate) {
      ensureMeta("robots", PRIVATE_ROBOTS);
      ensureMeta("googlebot", PRIVATE_ROBOTS);
      ensureMeta("yandex", PRIVATE_ROBOTS);
      removeCanonical();
      removePublicSeoMeta();
      removeHomeJsonLd();
      document.title = "Glosix";
      return;
    }

    removeMeta("robots");
    removeMeta("googlebot");
    removeMeta("yandex");

    // Главная — добавляем JSON-LD, og:url, og:image
    if (pathname === "/") {
      ensureHomeJsonLd();
      ensureOg("og:url", SITE_URL + "/");
      ensureOg("og:image", SITE_IMAGE);
      ensureMeta("twitter:image", SITE_IMAGE);
    } else {
      removeHomeJsonLd();
    }

    if (document.title === "Glosix") {
      document.title = DEFAULT_TITLE;
    }
  }, [pathname, search, hash]);
}
