import { useEffect, useState } from "react";
import { fetchFileContent } from "../api/client";
import { isProtectedFileContentUrl } from "../lib/attachmentImageUrl";
import { useAuthStore } from "../store/authStore";

/**
 * URL для превью вложения: blob во время отправки, иначе fetch с Bearer/cookie
 * (после обновления треда img на /api/files/… без заголовков даёт битую картинку).
 */
export function useAttachmentImageSrc(
  fileId: string,
  url: string | null | undefined,
  previewUrl: string | undefined,
): string | undefined {
  const token = useAuthStore((s) => s.token);
  const [src, setSrc] = useState<string | undefined>(() => {
    if (previewUrl?.startsWith("blob:")) return previewUrl;
    if (url && !isProtectedFileContentUrl(url)) return url;
    return previewUrl || url || undefined;
  });

  useEffect(() => {
    if (previewUrl?.startsWith("blob:")) {
      setSrc(previewUrl);
      return;
    }

    if (url && !isProtectedFileContentUrl(url)) {
      setSrc(url);
      return;
    }

    if (!fileId) {
      setSrc(previewUrl || url || undefined);
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
  }, [fileId, url, previewUrl, token]);

  return src;
}
