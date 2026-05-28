import { useEffect, useState } from "react";
import { bindMax, completeBindMax, fetchMe, loginWithInitData } from "../api/client";
import {
  getMaxInitData,
  getMaxStartParam,
  parseMaxBindToken,
  setMaxBindError,
} from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

/** JWT, then MAX deeplink bind, then MAX initData login, else guest-ready web session. */
export function useAuthBootstrap() {
  const { token, setAuth, setUser, clear } = useAuthStore();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        if (window.WebApp?.ready) window.WebApp.ready();

        const initData = getMaxInitData();
        const bindToken = parseMaxBindToken(getMaxStartParam());
        if (bindToken && initData) {
          try {
            const data = await completeBindMax(bindToken, initData);
            if (!cancelled) {
              setAuth(data.access_token, data.user);
              setReady(true);
              return;
            }
          } catch (err) {
            if (!cancelled) {
              setMaxBindError(err instanceof Error ? err.message : "Не удалось привязать MAX");
              setReady(true);
              return;
            }
          }
        }

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

        if (initData) {
          try {
            const data = await loginWithInitData(initData);
            if (!cancelled) {
              setAuth(data.access_token, data.user);
              setReady(true);
              return;
            }
          } catch {
            /* MAX: no email login screen; user stays guest until retry from bot */
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
  const initData = getMaxInitData();
  if (!initData) return;
  try {
    const user = await bindMax(token, initData);
    useAuthStore.getState().setUser(user);
  } catch {
    /* already linked */
  }
}
