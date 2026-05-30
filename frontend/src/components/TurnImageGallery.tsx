import { useCallback, useEffect, useMemo, useState } from "react";
import type { EntityImage } from "../api/client";

type Props = {
  images: EntityImage[];
};

const VISIBLE = 3;
const MIN_SIDE = 80;
const MAX_IMAGES = 5;

type LightboxState = {
  url: string;
  title: string;
  pageUrl: string;
};

function preloadImage(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.decoding = "async";
    img.onload = () => {
      resolve(img.naturalWidth >= MIN_SIDE && img.naturalHeight >= MIN_SIDE);
    };
    img.onerror = () => resolve(false);
    img.src = url;
  });
}

async function preloadGalleryImages(images: EntityImage[]): Promise<EntityImage[]> {
  const candidates = images.filter((img) => img.url).slice(0, MAX_IMAGES);
  if (!candidates.length) return [];

  const loaded = await Promise.all(
    candidates.map(async (img) => ({
      img,
      ok: await preloadImage(img.url),
    })),
  );

  return loaded.filter((entry) => entry.ok).map((entry) => entry.img);
}

export function TurnImageGallery({ images }: Props) {
  const [readyImages, setReadyImages] = useState<EntityImage[]>([]);
  const [start, setStart] = useState(0);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStart(0);
    setReadyImages([]);

    void preloadGalleryImages(images).then((loaded) => {
      if (!cancelled) setReadyImages(loaded);
    });

    return () => {
      cancelled = true;
    };
  }, [images]);

  const maxStart = Math.max(0, readyImages.length - VISIBLE);
  const clampedStart = Math.min(start, maxStart);
  const visibleImages = useMemo(
    () => readyImages.slice(clampedStart, clampedStart + VISIBLE),
    [readyImages, clampedStart],
  );

  const canPrev = clampedStart > 0;
  const canNext = clampedStart < maxStart;

  const goPrev = useCallback(() => {
    setStart((s) => Math.max(0, s - 1));
  }, []);

  const goNext = useCallback(() => {
    setStart((s) => Math.min(maxStart, s + 1));
  }, [maxStart]);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [lightbox]);

  if (!readyImages.length) return null;

  return (
    <>
      <div className="turn-image-gallery-preload" aria-hidden>
        {readyImages.map((img) => (
          <img key={`preload-${img.url}`} src={img.url} alt="" referrerPolicy="no-referrer" />
        ))}
      </div>

      <div className="turn-image-gallery" aria-label="Изображения">
        {canPrev && (
          <button
            type="button"
            className="turn-image-gallery-nav turn-image-gallery-nav--prev"
            onClick={goPrev}
            aria-label="Предыдущие фото"
          >
            <ChevronIcon direction="left" />
          </button>
        )}

        <div className="turn-image-gallery-track">
          {visibleImages.map((img) => (
            <button
              key={img.url}
              type="button"
              className="turn-image-gallery-item"
              onClick={() =>
                setLightbox({
                  url: img.url,
                  title: img.title || "",
                  pageUrl: img.page_url || img.url,
                })
              }
              title={img.title}
            >
              <img src={img.url} alt={img.title || ""} referrerPolicy="no-referrer" decoding="sync" />
            </button>
          ))}
        </div>

        {canNext && (
          <button
            type="button"
            className="turn-image-gallery-nav turn-image-gallery-nav--next"
            onClick={goNext}
            aria-label="Следующие фото"
          >
            <ChevronIcon direction="right" />
          </button>
        )}
      </div>

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
            aria-label={lightbox.title || "Фото"}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              className="image-lightbox-close"
              onClick={() => setLightbox(null)}
              aria-label="Закрыть"
            >
              ×
            </button>
            <img src={lightbox.url} alt={lightbox.title} referrerPolicy="no-referrer" decoding="sync" />
            {lightbox.pageUrl && lightbox.pageUrl !== lightbox.url && (
              <a
                className="image-lightbox-source"
                href={lightbox.pageUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Источник
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function ChevronIcon({ direction }: { direction: "left" | "right" }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d={direction === "left" ? "M15 6l-6 6 6 6" : "M9 6l6 6-6 6"}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
