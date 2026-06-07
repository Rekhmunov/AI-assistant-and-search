import { isMaxWebApp } from "./maxApp";
import { openExternalUrl } from "./openExternalUrl";

/** Открыть страницу оплаты ЮKassa (в MAX — через openLink, иначе новая вкладка). */
export function openPaymentUrl(url: string): void {
  if (isMaxWebApp() && window.WebApp?.openLink) {
    window.WebApp.openLink(url);
    return;
  }
  if (!openExternalUrl(url)) {
    window.location.assign(url);
  }
}
