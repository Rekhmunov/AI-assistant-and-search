/** Guest identity: HttpOnly cookie + X-Guest-Session header (для MAX WebView, где cookie ненадёжны). */

const STORAGE_KEY = "glosix_guest_session";

export function getGuestSessionHeader(): HeadersInit {
  try {
    const key = sessionStorage.getItem(STORAGE_KEY)?.trim();
    if (key) return { "X-Guest-Session": key };
  } catch {
    /* private mode / blocked storage */
  }
  return {};
}

export function saveGuestSession(key: string): void {
  const trimmed = key.trim();
  if (!trimmed) return;
  try {
    sessionStorage.setItem(STORAGE_KEY, trimmed);
  } catch {
    /* ignore */
  }
}

export function clearGuestSession(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
