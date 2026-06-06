import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, Navigate } from "react-router-dom";
import { fetchLegalByPath } from "../api/client";
import { t } from "../i18n";

export function LegalDocumentPage() {
  const { pathname } = useLocation();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["legal", pathname],
    queryFn: () => fetchLegalByPath(pathname),
    retry: false,
  });

  if (isError) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="page page-legal">
      <article className="legal-page-card">
        {isLoading || !data ? (
          <p className="muted-text">{t("pageLoading")}</p>
        ) : (
          <>
            <h1 className="legal-page-title">{data.title}</h1>
            <div
              className="legal-doc-html legal-page-body"
              dangerouslySetInnerHTML={{ __html: data.content_html }}
            />
          </>
        )}
        <p className="legal-page-back">
          <Link to="/">{t("backToSearch")}</Link>
        </p>
      </article>
    </div>
  );
}
