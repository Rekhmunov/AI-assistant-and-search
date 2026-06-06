import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";
import { fetchLegalRoutes } from "../api/client";
import { LegalDocumentPage } from "../pages/LegalDocumentPage";
import { t } from "../i18n";

/** Показывает юридический документ по public_path, иначе редирект на главную. */
export function LegalPathCatch() {
  const { pathname } = useLocation();
  const { data: routes = [], isLoading } = useQuery({
    queryKey: ["legal-routes"],
    queryFn: fetchLegalRoutes,
    staleTime: 60_000,
  });

  if (isLoading) {
    return <div className="app-boot-placeholder">{t("pageLoading")}</div>;
  }

  const match = routes.some((r) => r.public_path === pathname);
  if (!match) return <Navigate to="/" replace />;

  return <LegalDocumentPage />;
}
