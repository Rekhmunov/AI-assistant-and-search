import { useEffect, useState } from "react";
import {
  bindMax,
  completeBindMax,
  fetchMe,
  loginWithInitData,
  logoutSession,
  refreshAccessToken,
} from "../api/client";
import {
  getMaxInitData,
  getMaxStartParam,
  parseMaxBindToken,
  setMaxBindError,
  setMaxLoginError,
} from "../lib/maxApp";
import { HttpResponseError, isAuthFailureStatus, isTransientFailureStatus } from "../lib/httpError";
import { useAuthStore } from "../store/authStore";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function refreshAccessTokenWithRetry(): Promise<string> {
  let last: unknown;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const { access_token } = await refreshAccessToken();
      return access_token;
    } catch (err) {
      last = err;
      if (
        err instanceof HttpResponseError &&
        isTransientFailureStatus(err.status) &&
        attempt < 2
      ) {
        await sleep(1500);
        continue;
      }
      throw err;
    }
  }
  throw last;
}

async function trySilentRefresh(cancelled: () => boolean): Promise<string | null> {
  try {
    const accessToken = await refreshAccessTokenWithRetry();
    if (!cancelled()) {
      useAuthStore.getState().setToken(accessToken);
    }
    return accessToken;
  } catch (err) {
    if (
      err instanceof HttpResponseError &&
      !isTransientFailureStatus(err.status) &&
      !cancelled()
    ) {
      useAuthStore.getState().clear();
    }
    return null;
  }
}

/** JWT, then MAX deeplink bind, then MAX initData login, else guest-ready web session. */
export function useAuthBootstrap() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const isCancelled = () => cancelled;

    async function bootstrap() {
      try {
        if (window.WebApp?.ready) window.WebApp.ready();

        const initData = getMaxInitData();
        const bindToken = parseMaxBindToken(getMaxStartParam());
        if (bindToken && initData) {
          try {
            const data = await completeBindMax(bindToken, initData);
            if (!cancelled) {
              useAuthStore.getState().setAuth(data.access_token, data.user);
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

        let accessToken = useAuthStore.getState().token;
        if (!accessToken) {
          accessToken = await trySilentRefresh(isCancelled);
        }

        if (accessToken) {
          try {
            const user = await fetchMe(accessToken);
            if (!cancelled) {
              useAuthStore.getState().setUser(user);
              await tryBindMax(accessToken);
              setReady(true);
            }
            return;
          } catch (err) {
            if (err instanceof HttpResponseError && isAuthFailureStatus(err.status)) {
              if (!cancelled) {
                try {
                  await logoutSession();
                } catch {
                  /* ignore */
                }
                useAuthStore.getState().clear();
              }
            } else if (!cancelled) {
              setReady(true);
            }
            return;
          }
        }

        if (initData) {
          try {
            const data = await loginWithInitData(initData);
            if (!cancelled) {
              useAuthStore.getState().setAuth(data.access_token, data.user);
              setReady(true);
              return;
            }
          } catch (err) {
            if (!cancelled) {
              const message =
                err instanceof Error ? err.message : "Не удалось войти через MAX";
              setMaxLoginError(message);
            }
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
  }, []);

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
