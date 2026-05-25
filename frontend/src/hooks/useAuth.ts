import { useEffect, useState } from "react";
import { fetchMe } from "../api/client";
import { useAuthStore } from "../store/authStore";

/** Validates stored JWT; clears invalid token. */
export function useAuthBootstrap() {
  const { token, setUser, clear } = useAuthStore();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        if (token) {
          try {
            const user = await fetchMe(token);
            if (!cancelled) {
              setUser(user);
              setReady(true);
            }
            return;
          } catch {
            clear();
          }
        }

        if (!cancelled) setReady(true);
      } catch {
        if (!cancelled) {
          setError("Ошибка загрузки");
          setReady(true);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [token, clear, setUser]);

  return { ready, error };
}
