import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { hasMaxWebAppHashInUrl, isMaxWebApp } from "../lib/maxApp";

const PRIVATE_ROUTE_PREFIXES = ["/thread", "/history", "/profile", "/login", "/source-view"] as const;

const DEFAULT_TITLE = "Glosix - умный поиск с источниками, ИИ чат";
const PUBLIC_CONTENT_PREFIXES = ["/blog"] as const;
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive";

function isPrivateAppRoute(pathname: string): boolean {
  return PRIVATE_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

function isNonIndexableSession(): boolean {
  return isMaxWebApp() || hasMaxWebAppHashInUrl();
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
    const isPrivate = isPrivateAppRoute(pathname) || isNonIndexableSession();
    if (isPrivate) {
      ensureMeta("robots", PRIVATE_ROBOTS);
      ensureMeta("googlebot", PRIVATE_ROBOTS);
      document.title = "Glosix";
      return;
    }

    const isPublicContent = PUBLIC_CONTENT_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    );
    if (!isPublicContent) {
      removeMeta("robots");
      removeMeta("googlebot");
      if (document.title === "Glosix") {
        document.title = DEFAULT_TITLE;
      }
    }
  }, [pathname]);
}
