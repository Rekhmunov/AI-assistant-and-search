import { useEffect, useState } from "react";
import { fetchMe, login } from "../api/client";
import { useAuthStore } from "../store/authStore";

const DEV_INIT_DATA = "user=%7B%22id%22%3A1%2C%22first_name%22%3A%22Dev%22%7D&auth_date=9999999999";

export function useAuthBootstrap() {
  const { token, setAuth, setUser } = useAuthStore();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const initData = window.WebApp?.initData || DEV_INIT_DATA;
        if (window.WebApp?.ready) window.WebApp.ready();

        if (!token) {
          const data = await login(initData);
          if (!cancelled) setAuth(data.access_token, data.user);
        } else {
          const user = await fetchMe(token);
          if (!cancelled) setUser(user);
        }
      } catch {
        if (!cancelled) setError("Не удалось войти");
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  return { ready, error };
}
