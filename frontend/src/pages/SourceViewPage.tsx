import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";
import {
  detectIframeEmbedState,
  parseSourceViewUrl,
  SOURCE_VIEW_EMBED_HINT_DELAY_MS,
} from "../lib/sourceView";

export function SourceViewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const url = parseSourceViewUrl(searchParams.get("url"));
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const loadSettledRef = useRef(false);
  const [showEmbedHint, setShowEmbedHint] = useState(false);

  const goBack = useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }
    navigate("/", { replace: true });
  }, [navigate]);

  const openExternal = useCallback(() => {
    if (!url) return;
    if (window.WebApp?.openLink) {
      window.WebApp.openLink(url);
      return;
    }
    window.open(url, "_blank", "noopener,noreferrer");
  }, [url]);

  const syncEmbedHint = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    setShowEmbedHint(detectIframeEmbedState(iframe) === "blocked");
  }, []);

  const handleIframeLoad = useCallback(() => {
    loadSettledRef.current = true;
    syncEmbedHint();
  }, [syncEmbedHint]);

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

  useEffect(() => {
    if (!url) return;

    setShowEmbedHint(false);
    loadSettledRef.current = false;

    const timer = window.setTimeout(() => {
      if (loadSettledRef.current) {
        syncEmbedHint();
        return;
      }
      setShowEmbedHint(true);
    }, SOURCE_VIEW_EMBED_HINT_DELAY_MS);

    return () => window.clearTimeout(timer);
  }, [url, syncEmbedHint]);

  if (!url) {
    return <Navigate to="/" replace />;
  }

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

      <div className="source-view-frame-wrap">
        <iframe
          ref={iframeRef}
          className="source-view-frame"
          src={url}
          title={t("sources")}
          referrerPolicy="no-referrer-when-downgrade"
          onLoad={handleIframeLoad}
        />

        {showEmbedHint && (
          <div className="source-view-embed-hint" role="status">
            <p className="source-view-embed-hint-text">{t("sourceViewEmbedBlocked")}</p>
            <button type="button" className="source-view-embed-hint-btn" onClick={openExternal}>
              {t("sourceViewOpenExternal")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
