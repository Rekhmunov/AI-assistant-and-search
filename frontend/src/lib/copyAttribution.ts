import { t } from "../i18n";

export const GLOSIX_PUBLIC_URL = "https://app.glosix.ru";

export function isProPlan(plan: string | null | undefined): boolean {
  return plan === "pro";
}

/** Текст для буфера обмена / «Поделиться»: на Free — с припиской Glosix. */
export function buildCopyText(text: string, isPro: boolean): string {
  const body = text.trim();
  if (!body) return "";
  if (isPro) return body;
  const attribution = t("copyAttribution", { url: GLOSIX_PUBLIC_URL });
  return `${body}\n\n${attribution}`;
}
