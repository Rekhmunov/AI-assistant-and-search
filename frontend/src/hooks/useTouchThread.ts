import { useCallback, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

/**
 * Снимает флаг is_new с агент-треда при первом изменении формы.
 * Тред становится виден в истории как черновик.
 * Повторные вызовы игнорируются (only once per mount).
 */
export function useTouchThread(threadId: string, token: string | null) {
  const touched = useRef(false);

  return useCallback(async () => {
    if (touched.current) return;
    touched.current = true;
    try {
      await fetch(`${API_BASE}/api/agent/threads/${threadId}/touch`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      // non-critical — ignore
    }
  }, [threadId, token]);
}
