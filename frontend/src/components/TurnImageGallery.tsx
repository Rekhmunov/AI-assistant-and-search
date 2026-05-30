import { useMemo, useState } from "react";
import type { EntityImage } from "../api/client";

type Props = {
  images: EntityImage[];
};

export function TurnImageGallery({ images }: Props) {
  const [failed, setFailed] = useState<Set<string>>(() => new Set());

  const visible = useMemo(
    () => images.filter((img) => img.url && !failed.has(img.url)),
    [images, failed],
  );

  if (!visible.length) return null;

  const markFailed = (url: string) => {
    setFailed((prev) => {
      if (prev.has(url)) return prev;
      const next = new Set(prev);
      next.add(url);
      return next;
    });
  };

  return (
    <div className="turn-image-gallery" aria-label="Images">
      <div className="turn-image-gallery-track">
        {visible.map((img) => (
          <a
            key={img.url}
            className="turn-image-gallery-item"
            href={img.page_url || img.url}
            target="_blank"
            rel="noopener noreferrer"
            title={img.title}
          >
            <img
              src={img.url}
              alt={img.title || ""}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => markFailed(img.url)}
            />
          </a>
        ))}
      </div>
    </div>
  );
}
