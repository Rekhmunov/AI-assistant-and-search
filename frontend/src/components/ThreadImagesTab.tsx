import { useEffect, useMemo, useState } from "react";
import type { EntityImage } from "../api/client";
import { preloadEntityImages } from "../lib/preloadEntityImages";
import { faviconUrl, sourceDomainLabel } from "../lib/sourceDomainLabel";
import type { ThreadImageGroup } from "../lib/threadImageGroups";
import { t } from "../i18n";

type Props = {
  groups: ThreadImageGroup[];
  loading?: boolean;
};

type LightboxState = {
  url: string;
  title: string;
  pageUrl: string;
};

type ReadyGroup = ThreadImageGroup & { readyImages: EntityImage[] };

function groupsToReady(groups: ThreadImageGroup[]): ReadyGroup[] {
  return groups
    .filter((group) => group.images.length > 0)
    .map((group) => ({ ...group, readyImages: group.images }));
}

export function ThreadImagesTab({ groups, loading = false }: Props) {
  const [readyGroups, setReadyGroups] = useState<ReadyGroup[]>(() => groupsToReady(groups));
  const [preparing, setPreparing] = useState(false);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);
  const groupsKey = useMemo(
    () => groups.map((g) => `${g.turnKey}:${g.images.map((i) => i.url).join("|")}`).join(";"),
    [groups],
  );

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
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [lightbox]);

  const totalRaw = groups.reduce((sum, group) => sum + group.images.length, 0);
  const totalReady = readyGroups.reduce((sum, group) => sum + group.readyImages.length, 0);
  const showLoading = loading || (preparing && totalReady === 0 && totalRaw > 0);

  return (
    <div className="thread-images-tab">
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
              return (
                <li key={`${group.turnKey}-${img.url}`} className="turn-images-grid-item">
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
                    <img
                      src={img.url}
                      alt={img.title || domain || ""}
                      referrerPolicy="no-referrer"
                      loading="lazy"
                    />
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
        </section>
      ))}

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
