const STORAGE_KEY = "glosix_cookie_consent";

export type StoredCookieConsent = {
  version_id: string;
  accepted_at: string;
};

export function readCookieConsent(): StoredCookieConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredCookieConsent;
    if (!parsed?.version_id) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeCookieConsent(versionId: string): void {
  const payload: StoredCookieConsent = {
    version_id: versionId,
    accepted_at: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

export function isCookieConsentCurrent(versionId: string | undefined): boolean {
  if (!versionId) return true;
  const stored = readCookieConsent();
  return stored?.version_id === versionId;
}
