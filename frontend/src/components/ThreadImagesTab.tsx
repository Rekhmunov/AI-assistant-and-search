import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EntityImage } from "../api/client";
import { isGeneratedImageUrl } from "../lib/generatedImageUrl";
import { preloadEntityImages } from "../lib/preloadEntityImages";
import { faviconUrl, sourceDomainLabel } from "../lib/sourceDomainLabel";
import type { ThreadImageGroup } from "../lib/threadImageGroups";
import { t } from "../i18n";

type Props = {
  groups: ThreadImageGroup[];
  loading?: boolean;
};

type LightboxImage = {
  url: string;
  title: string;
  pageUrl: string;
};

type ReadyGroup = ThreadImageGroup & { readyImages: EntityImage[] };

const SWIPE_MIN_PX = 48;

function groupsToReady(groups: ThreadImageGroup[]): ReadyGroup[] {
  return groups
    .filter((group) => group.images.length > 0)
    .map((group) => ({ ...group, readyImages: group.images }));
}

function SourceLink({ href, className }: { href: string; className: string }) {
  const domain = sourceDomainLabel(href);
  return (
    <a className={className} href={href} target="_blank" rel="noopener noreferrer">
      <img
        className="image-lightbox-source-icon"
        src={faviconUrl(href)}
        alt=""
        width={16}
        height={16}
        loading="lazy"
        decoding="async"
      />
      <span>{domain || href}</span>
    </a>
  );
}

export function ThreadImagesTab({ groups, loading = false }: Props) {
  const [readyGroups, setReadyGroups] = useState<ReadyGroup[]>(() => groupsToReady(groups));
  const [preparing, setPreparing] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);
  const groupsKey = useMemo(
    () => groups.map((g) => `${g.turnKey}:${g.images.map((i) => i.url).join("|")}`).join(";"),
    [groups],
  );

  const flatImages = useMemo<LightboxImage[]>(() => {
    const items: LightboxImage[] = [];
    for (const group of readyGroups) {
      for (const img of group.readyImages) {
        items.push({
          url: img.url,
          title: img.title || "",
          pageUrl: img.page_url || img.url,
        });
      }
    }
    return items;
  }, [readyGroups]);

  const lightbox = lightboxIndex !== null ? flatImages[lightboxIndex] ?? null : null;
  const canPrev = lightboxIndex !== null && lightboxIndex > 0;
  const canNext = lightboxIndex !== null && lightboxIndex < flatImages.length - 1;

  const goPrev = useCallback(() => {
    setLightboxIndex((idx) => (idx !== null && idx > 0 ? idx - 1 : idx));
  }, []);

  const goNext = useCallback(() => {
    setLightboxIndex((idx) =>
      idx !== null && idx < flatImages.length - 1 ? idx + 1 : idx,
    );
  }, [flatImages.length]);

  useEffect(() => {
    const initial = groupsToReady(groups);
    setReadyGroups(initial);
    if (!initial.length) {
      setPreparing(false);
      return;
    }

    let cancelled = false;
    setPreparing(true);

    void (async () => {
      const loaded: ReadyGroup[] = [];
      for (const group of groups) {
        const validated = await preloadEntityImages(group.images);
        if (cancelled) return;
        const readyImages = validated.length > 0 ? validated : group.images;
        if (readyImages.length > 0) {
          loaded.push({ ...group, readyImages });
        }
      }
      if (!cancelled) {
        setReadyGroups(loaded.length > 0 ? loaded : initial);
        setPreparing(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [groupsKey, groups]);

  useEffect(() => {
    if (lightboxIndex === null) return;
    if (lightboxIndex >= flatImages.length) {
      setLightboxIndex(flatImages.length > 0 ? flatImages.length - 1 : null);
    }
  }, [flatImages.length, lightboxIndex]);

  useEffect(() => {
    if (lightboxIndex === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightboxIndex(null);
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [lightboxIndex, goPrev, goNext]);

  const onTouchStart = (e: React.TouchEvent) => {
    const touch = e.changedTouches[0] ?? e.touches[0];
    if (!touch) return;
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    const start = touchStartRef.current;
    const touch = e.changedTouches[0];
    touchStartRef.current = null;
    if (!start || !touch) return;

    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) <= Math.abs(dy)) return;

    if (dx < 0) goNext();
    else goPrev();
  };

  const totalRaw = groups.reduce((sum, group) => sum + group.images.length, 0);
  const totalReady = readyGroups.reduce((sum, group) => sum + group.readyImages.length, 0);
  const showLoading = loading || (preparing && totalReady === 0 && totalRaw > 0);

  let flatIndex = 0;

  return (
    <div className="thread-images-tab" id="thread-images-top">
      {showLoading && (
        <p className="thread-images-tab-status">{t("imagesLoading")}</p>
      )}

      {!showLoading && totalReady === 0 && (
        <p className="thread-images-tab-status">{t("imagesEmpty")}</p>
      )}

      {readyGroups.map((group) => (
        <section key={group.turnKey} className="thread-images-group">
          <h3 className="thread-images-group-title">{group.query.trim()}</h3>
          <ul className="turn-images-grid">
            {group.readyImages.map((img) => {
              const sourceHref = img.page_url || img.url;
              const domain = sourceDomainLabel(sourceHref);
              const index = flatIndex;
              flatIndex += 1;
              const generated = isGeneratedImageUrl(img.url);
              return (
                <li
                  key={`${group.turnKey}-${img.url}`}
                  className={`turn-images-grid-item${generated ? " turn-images-grid-item--generated" : ""}`}
                >
                  <button
                    type="button"
                    className={`turn-images-grid-thumb${generated ? " turn-images-grid-thumb--generated" : ""}`}
                    onClick={() => setLightboxIndex(index)}
                  >
                    <img
                      src={img.url}
                      alt={img.title || domain || ""}
                      referrerPolicy="no-referrer"
                      loading="lazy"
                    />
                  </button>
                  {!generated && (
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
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {lightbox && lightboxIndex !== null && (
        <div
          className="image-lightbox-overlay"
          role="presentation"
          onClick={() => setLightboxIndex(null)}
        >
          <button
            type="button"
            className="image-lightbox-close"
            onClick={() => setLightboxIndex(null)}
            aria-label={t("close")}
          >
            ×
          </button>
          <div
            className="image-lightbox"
            role="dialog"
            aria-modal="true"
            aria-label={lightbox.title || t("turnTabImages")}
            onClick={(e) => e.stopPropagation()}
          >
            {canPrev && (
              <button
                type="button"
                className="image-lightbox-nav image-lightbox-nav--prev"
                onClick={goPrev}
                aria-label={t("imageLightboxPrev")}
              >
                ‹
              </button>
            )}
            {canNext && (
              <button
                type="button"
                className="image-lightbox-nav image-lightbox-nav--next"
                onClick={goNext}
                aria-label={t("imageLightboxNext")}
              >
                ›
              </button>
            )}

            <div
              className="image-lightbox-stage"
              onTouchStart={onTouchStart}
              onTouchEnd={onTouchEnd}
            >
              <img
                key={lightbox.url}
                src={lightbox.url}
                alt={lightbox.title}
                referrerPolicy="no-referrer"
                decoding="sync"
                draggable={false}
              />
            </div>

            {lightbox.pageUrl && (
              <SourceLink href={lightbox.pageUrl} className="image-lightbox-source" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
