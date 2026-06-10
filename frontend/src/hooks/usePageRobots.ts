import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { hasMaxWebAppHashInUrl, isMaxWebApp } from "../lib/maxApp";
import { shouldNoindexPage } from "../lib/pageRobots";

const DEFAULT_TITLE = "Glosix - умный поиск с источниками, ИИ чат";
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive";

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

function removeMeta(name: string) {
  document.querySelector(`meta[name="${name}"]`)?.remove();
}

function removeCanonical() {
  document.querySelector('link[rel="canonical"]')?.remove();
}

/** Prevent search engines from indexing private SPA routes (threads, history, profile). */
export function usePageRobots() {
  const { pathname, search, hash } = useLocation();

  useEffect(() => {
    const isPrivate =
      shouldNoindexPage(pathname, search, hash) || isMaxWebApp() || hasMaxWebAppHashInUrl();
    if (isPrivate) {
      ensureMeta("robots", PRIVATE_ROBOTS);
      ensureMeta("googlebot", PRIVATE_ROBOTS);
      ensureMeta("yandex", "noindex, nofollow");
      removeCanonical();
      document.title = "Glosix";
      return;
    }

    removeMeta("robots");
    removeMeta("googlebot");
    removeMeta("yandex");
    if (document.title === "Glosix") {
      document.title = DEFAULT_TITLE;
    }
  }, [pathname, search, hash]);
}
