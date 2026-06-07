import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchLegalBySlug, fetchLegalRoutes, recordLegalConsent } from "../api/client";
import { isCookieConsentCurrent, writeCookieConsent } from "../lib/cookieConsent";
import { t } from "../i18n";
import { LegalDocumentModal } from "./LegalDocumentModal";
import { useAuthStore } from "../store/authStore";

type Props = {
  onAccepted?: () => void;
};

export function CookieBanner({ onAccepted }: Props) {
  const token = useAuthStore((s) => s.token);
  const [open, setOpen] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data: routes } = useQuery({
    queryKey: ["legal-routes"],
    queryFn: fetchLegalRoutes,
    staleTime: 60_000,
  });

  const cookiesMeta = routes?.find((r) => r.slug === "cookies");

  const { data: cookiesDoc, isLoading: cookiesLoading } = useQuery({
    queryKey: ["legal-cookies-doc"],
    queryFn: () => fetchLegalBySlug("cookies"),
    enabled: modalOpen,
  });

  if (!open || !cookiesMeta) return null;
  if (isCookieConsentCurrent(cookiesMeta.version_id)) return null;

  const accept = async () => {
    if (!cookiesMeta.version_id || busy) return;
    setBusy(true);
    try {
      writeCookieConsent(cookiesMeta.version_id);
      if (token) {
        await recordLegalConsent(token, {
          consents: [{ slug: "cookies", version_id: cookiesMeta.version_id }],
          source: "cookie_banner",
          consent_method: "button_accept",
        });
      }
      setOpen(false);
      onAccepted?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="cookie-banner" role="dialog" aria-label={t("cookieBannerAriaLabel")}>
        <p className="cookie-banner-text">
          {t("cookieBannerPrefix")}
          <button type="button" className="cookie-banner-link" onClick={() => setModalOpen(true)}>
            {t("cookieBannerLink")}
          </button>
          {t("cookieBannerSuffix")}
        </p>
        <button type="button" className="btn-primary cookie-banner-btn" disabled={busy} onClick={() => void accept()}>
          {busy ? "…" : t("cookieBannerOk")}
        </button>
      </div>

      {modalOpen && (
        <LegalDocumentModal
          title={cookiesDoc?.title ?? t("cookiePolicyTitle")}
          contentHtml={cookiesDoc?.content_html ?? ""}
          loading={cookiesLoading}
          onClose={() => setModalOpen(false)}
        />
      )}
    </>
  );
}
