import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const PRIVATE_ROUTE_PREFIXES = ["/thread", "/history", "/profile", "/login", "/source-view"] as const;

const DEFAULT_TITLE = "Glosix - умный поиск с источниками, ИИ чат";
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive";

function isPrivateAppRoute(pathname: string): boolean {
  return PRIVATE_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

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

/** Prevent search engines from indexing private SPA routes (threads, history, profile). */
export function usePageRobots() {
  const { pathname } = useLocation();

  useEffect(() => {
    const isPrivate = isPrivateAppRoute(pathname);
    if (isPrivate) {
      ensureMeta("robots", PRIVATE_ROBOTS);
      ensureMeta("googlebot", PRIVATE_ROBOTS);
      document.title = "Glosix";
      return;
    }

    removeMeta("robots");
    removeMeta("googlebot");
    if (document.title === "Glosix") {
      document.title = DEFAULT_TITLE;
    }
  }, [pathname]);
}
