/** Guest identity is carried by HttpOnly cookie (credentials: include). No localStorage. */

export function getGuestSessionHeader(): HeadersInit {
  return {};
}

export function saveGuestSession(_key: string): void {
  /* cookie set by API response */
}

export function clearGuestSession(): void {
  /* cookie cleared on login / logout via API */
}
