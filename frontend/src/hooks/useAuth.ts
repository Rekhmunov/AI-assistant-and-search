import { useEffect, useState } from "react";
import { bindMax, fetchMe, loginWithInitData } from "../api/client";
import { useAuthStore } from "../store/authStore";

/** Validates stored token or legacy MAX initData; clears invalid token. */
export function useAuthBootstrap() {
  const { token, setAuth, setUser, clear } = useAuthStore();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        if (window.WebApp?.ready) window.WebApp.ready();

        if (token) {
          try {
            const user = await fetchMe(token);
            if (!cancelled) {
              setUser(user);
              await tryBindMax(token);
              setReady(true);
            }
            return;
          } catch {
            clear();
          }
        }

        const initData = window.WebApp?.initData?.trim();
        if (initData) {
          try {
            const data = await loginWithInitData(initData);
            if (!cancelled) {
              setAuth(data.access_token, data.user);
              setReady(true);
              return;
            }
          } catch {
            /* show email login */
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
  }, [token, clear, setAuth, setUser]);

  return { ready, error };
}

async function tryBindMax(token: string) {
  const initData = window.WebApp?.initData?.trim();
  if (!initData) return;
  try {
    const user = await bindMax(token, initData);
    useAuthStore.getState().setUser(user);
  } catch {
    /* already linked */
  }
}
