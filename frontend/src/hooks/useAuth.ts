import { useEffect, useState } from "react";
import {
  bindMax,
  completeBindMax,
  fetchMe,
  loginWithInitData,
  refreshAccessToken,
} from "../api/client";
import {
  captureMaxInitDataFromUrl,
  getMaxInitData,
  getMaxStartParam,
  parseMaxBindToken,
  setMaxBindError,
  setMaxLoginError,
  stripMaxWebAppHashFromUrl,
  waitForMaxWebApp,
} from "../lib/maxApp";
import { HttpResponseError, isAuthFailureStatus, isTransientFailureStatus } from "../lib/httpError";
import { stripPrivateQueryParamsFromUrl } from "../lib/pageRobots";
import { useAuthStore, waitForAuthHydration } from "../store/authStore";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const HYDRATION_TIMEOUT_MS = 1500;
const MAX_BRIDGE_TIMEOUT_MS = 5000;
const AUTH_TASK_TIMEOUT_MS = 8000;

async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return Promise.race([promise, sleep(ms).then(() => null)]);
}

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
    const accessToken = await withTimeout(refreshAccessTokenWithRetry(), AUTH_TASK_TIMEOUT_MS);
    if (!accessToken) return null;
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

async function resolveAccessToken(cancelled: () => boolean): Promise<string | null> {
  let accessToken = useAuthStore.getState().token;

  if (accessToken) {
    try {
      const user = await withTimeout(fetchMe(accessToken), AUTH_TASK_TIMEOUT_MS);
      if (user && !cancelled()) {
        useAuthStore.getState().setUser(user);
      }
      if (user) return accessToken;
    } catch (err) {
      if (!(err instanceof HttpResponseError && isAuthFailureStatus(err.status))) {
        return accessToken;
      }
    }
  }

  return trySilentRefresh(cancelled);
}

async function tryBindMax(token: string) {
  const initData = getMaxInitData();
  if (!initData) return;
  try {
    const user = await withTimeout(bindMax(token, initData), 4000, null);
    if (user) useAuthStore.getState().setUser(user);
  } catch {
    /* already linked */
  }
}

async function runBackgroundAuth(cancelled: () => boolean) {
  await Promise.race([waitForMaxWebApp(MAX_BRIDGE_TIMEOUT_MS), sleep(MAX_BRIDGE_TIMEOUT_MS)]);
  if (cancelled()) return;

  captureMaxInitDataFromUrl();
  stripMaxWebAppHashFromUrl();
  stripPrivateQueryParamsFromUrl();

  const initData = getMaxInitData();
  const bindToken = parseMaxBindToken(getMaxStartParam());

  if (bindToken && initData) {
    try {
      const data = await withTimeout(
        completeBindMax(bindToken, initData),
        AUTH_TASK_TIMEOUT_MS,
        null,
      );
      if (data && !cancelled()) {
        useAuthStore.getState().setAuth(data.access_token, data.user);
        return;
      }
    } catch (err) {
      if (!cancelled()) {
        setMaxBindError(err instanceof Error ? err.message : "Не удалось привязать MAX");
      }
      return;
    }
  }

  const accessToken = await resolveAccessToken(cancelled);
  if (cancelled()) return;

  if (accessToken) {
    void tryBindMax(accessToken);
    return;
  }

  if (initData) {
    try {
      const data = await withTimeout(loginWithInitData(initData), AUTH_TASK_TIMEOUT_MS, null);
      if (data && !cancelled()) {
        useAuthStore.getState().setAuth(data.access_token, data.user);
      }
    } catch (err) {
      if (!cancelled()) {
        const message = err instanceof Error ? err.message : "Не удалось войти через MAX";
        setMaxLoginError(message);
      }
    }
  }
}

// Proactive token refresh — runs every 50 min while app is open.
// Access token TTL is 60 min; refreshing at 50 min prevents expiry-related
// "limits exceeded" errors for Pro users staying in the MAX mini-app.
const TOKEN_REFRESH_INTERVAL_MS = 50 * 60 * 1000; // 50 minutes

function startTokenRefreshInterval(): () => void {
  const id = setInterval(async () => {
    const { token } = useAuthStore.getState();
    if (!token) return; // not logged in — skip
    try {
      const { access_token } = await refreshAccessToken();
      useAuthStore.getState().setToken(access_token);
    } catch {
      // Refresh failed (offline / session expired) — will retry next tick
    }
  }, TOKEN_REFRESH_INTERVAL_MS);

  return () => clearInterval(id);
}

/** UI сразу после hydration; MAX login и refresh — в фоне. */
export function useAuthBootstrap() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const isCancelled = () => cancelled;

    // Start proactive token refresh for long sessions (MAX mini-app)
    const stopRefresh = startTokenRefreshInterval();

    async function bootstrap() {
      try {
        captureMaxInitDataFromUrl();
        try {
          window.WebApp?.ready?.();
        } catch {
          /* MAX bridge may be partial on desktop */
        }

        await Promise.race([waitForAuthHydration(), sleep(HYDRATION_TIMEOUT_MS)]);
        if (cancelled) return;

        if (!cancelled) setReady(true);

        void runBackgroundAuth(isCancelled);
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
      stopRefresh();
    };
  }, []);

  return { ready, error };
}
