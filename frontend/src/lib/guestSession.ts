const STORAGE_KEY = "glosix-guest-session";

export function getGuestSessionHeader(): HeadersInit {
  const key = localStorage.getItem(STORAGE_KEY);
  return key ? { "X-Guest-Session": key } : {};
}

export function saveGuestSession(key: string): void {
  localStorage.setItem(STORAGE_KEY, key);
}

export function clearGuestSession(): void {
  localStorage.removeItem(STORAGE_KEY);
}
