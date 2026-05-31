import { useCallback, useEffect } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";
import { parseSourceViewUrl } from "../lib/sourceView";

export function SourceViewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const url = parseSourceViewUrl(searchParams.get("url"));

  const goBack = useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate("/", { replace: true });
  }, [navigate]);

  useEffect(() => {
    if (!url) return;

    const backButton = window.WebApp?.BackButton;
    if (!isMaxWebApp() || !backButton) return;

    backButton.show();
    backButton.onClick(goBack);
    return () => {
      backButton.offClick(goBack);
      backButton.hide();
    };
  }, [url, goBack]);

  if (!url) {
    return <Navigate to="/" replace />;
  }

  const openExternal = () => {
    if (window.WebApp?.openLink) {
      window.WebApp.openLink(url);
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const host = url.replace(/^https?:\/\//, "").split("/")[0];

  return (
    <div className="page source-view-page">
      <header className="source-view-header">
        {!isMaxWebApp() && (
          <button type="button" className="source-view-back" onClick={goBack}>
            {t("back")}
          </button>
        )}
        <span className="source-view-host" title={url}>
          {host}
        </span>
        <button type="button" className="source-view-open-external" onClick={openExternal}>
          {t("sourceViewOpenExternal")}
        </button>
      </header>

      <iframe
        className="source-view-frame"
        src={url}
        title={t("sources")}
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
