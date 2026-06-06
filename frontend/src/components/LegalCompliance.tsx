import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchLegalRoutes } from "../api/client";
import { isCookieConsentCurrent } from "../lib/cookieConsent";
import { CookieBanner } from "./CookieBanner";
import { ReconsentGate } from "./ReconsentGate";

export function LegalCompliance() {
  const [cookieTick, setCookieTick] = useState(0);

  const { data: routes } = useQuery({
    queryKey: ["legal-routes"],
    queryFn: fetchLegalRoutes,
    staleTime: 60_000,
  });

  const cookiesVersionId = routes?.find((r) => r.slug === "cookies")?.version_id;
  const cookiesResolved = useMemo(
    () => isCookieConsentCurrent(cookiesVersionId),
    [cookiesVersionId, cookieTick],
  );

  return (
    <>
      <CookieBanner onAccepted={() => setCookieTick((n) => n + 1)} />
      <ReconsentGate cookiesResolved={cookiesResolved} />
    </>
  );
}
