/**
 * Обрабатывает deep-link из MAX mini-app: startapp=thread_{uuid} или startapp=history.
 * Вызывается после авторизации; перенаправляет на нужный раздел.
 */
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getMaxStartParam } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

const THREAD_PREFIX = "thread_";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function useMaxDeepLink() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const handled = useRef(false);

  useEffect(() => {
    if (!token || handled.current) return;

    const param = getMaxStartParam().trim();
    if (!param) return;

    handled.current = true;

    if (param === "history") {
      navigate("/history", { replace: true });
      return;
    }

    if (param.startsWith(THREAD_PREFIX)) {
      const threadId = param.slice(THREAD_PREFIX.length);
      if (UUID_RE.test(threadId)) {
        navigate(`/thread/${threadId}`, { replace: true });
      }
    }
  }, [token, navigate]);
}
