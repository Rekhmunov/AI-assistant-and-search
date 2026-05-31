import { useEffect, useState } from "react";
import type { EntityImage } from "../api/client";
import { preloadEntityImages } from "../lib/preloadEntityImages";
import { faviconUrl, sourceDomainLabel } from "../lib/sourceDomainLabel";
import { t } from "../i18n";

type Props = {
  query: string;
  images: EntityImage[];
  loading?: boolean;
};

type LightboxState = {
  url: string;
  title: string;
  pageUrl: string;
};

export function TurnImagesTab({ query, images, loading = false }: Props) {
  const [readyImages, setReadyImages] = useState<EntityImage[]>([]);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  useEffect(() => {
    let cancelled = false;
    setReadyImages([]);

    void preloadEntityImages(images).then((loaded) => {
      if (!cancelled) setReadyImages(loaded);
    });

    return () => {
      cancelled = true;
    };
  }, [images]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [lightbox]);

  const title = query.trim()
    ? t("imagesResultsFor", { query: query.trim() })
    : t("turnTabImages");

  return (
    <div className="turn-images-tab">
      <p className="turn-images-tab-heading">{title}</p>

      {loading && readyImages.length === 0 && (
        <p className="turn-images-tab-status">{t("imagesLoading")}</p>
      )}

      {!loading && readyImages.length === 0 && (
        <p className="turn-images-tab-status">{t("imagesEmpty")}</p>
      )}

      {readyImages.length > 0 && (
        <ul className="turn-images-grid">
          {readyImages.map((img) => {
            const sourceHref = img.page_url || img.url;
            const domain = sourceDomainLabel(sourceHref);
            return (
              <li key={img.url} className="turn-images-grid-item">
                <button
                  type="button"
                  className="turn-images-grid-thumb"
                  onClick={() =>
                    setLightbox({
                      url: img.url,
                      title: img.title || "",
                      pageUrl: sourceHref,
                    })
                  }
                >
                  <img src={img.url} alt={img.title || domain || ""} referrerPolicy="no-referrer" loading="lazy" />
                </button>
                <a
                  className="turn-images-grid-source"
                  href={sourceHref}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    className="turn-images-grid-source-icon"
                    src={faviconUrl(sourceHref)}
                    alt=""
                    width={16}
                    height={16}
                    loading="lazy"
                    decoding="async"
                  />
                  <span>{domain || sourceHref}</span>
                </a>
              </li>
            );
          })}
        </ul>
      )}

      {lightbox && (
        <div
          className="image-lightbox-overlay"
          role="presentation"
          onClick={() => setLightbox(null)}
        >
          <div
            className="image-lightbox"
            role="dialog"
            aria-modal="true"
            aria-label={lightbox.title || t("turnTabImages")}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="image-lightbox-close"
              onClick={() => setLightbox(null)}
              aria-label={t("close")}
            >
              ×
            </button>
            <img src={lightbox.url} alt={lightbox.title} referrerPolicy="no-referrer" decoding="sync" />
            {lightbox.pageUrl && (
              <a
                className="image-lightbox-source"
                href={lightbox.pageUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                {t("sourceLink")}
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
