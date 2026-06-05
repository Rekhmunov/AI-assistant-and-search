import { useEffect, useState } from "react";
import { fetchFileContent } from "../api/client";
import { isProtectedFileContentUrl } from "../lib/attachmentImageUrl";
import { parseGeneratedFileId } from "../lib/generatedImageUrl";
import { useAuthStore } from "../store/authStore";

/**
 * Превью защищённых /api/files/…/content: fetch с Bearer/cookie → blob URL.
 * Прямой <img src> без заголовков даёт битую картинку (MAX WebApp, истёкший JWT).
 */
export function useProtectedImageSrc(url: string | null | undefined): string | undefined {
  const token = useAuthStore((s) => s.token);
  const [src, setSrc] = useState<string | undefined>(() => {
    const u = (url || "").trim();
    if (!u || isProtectedFileContentUrl(u)) return undefined;
    return u;
  });

  useEffect(() => {
    const u = (url || "").trim();
    if (!u) {
      setSrc(undefined);
      return;
    }
    if (!isProtectedFileContentUrl(u)) {
      setSrc(u);
      return;
    }

    const fileId = parseGeneratedFileId(u);
    if (!fileId) {
      setSrc(undefined);
      return;
    }

    let objectUrl: string | null = null;
    let cancelled = false;

    void (async () => {
      try {
        const blob = await fetchFileContent(token, fileId);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch {
        if (!cancelled) setSrc(undefined);
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url, token]);

  return src;
}
