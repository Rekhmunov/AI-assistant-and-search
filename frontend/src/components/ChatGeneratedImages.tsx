import { useEffect, useState } from "react";
import type { EntityImage } from "../api/client";

type LightboxState = {
  url: string;
  title: string;
};

type Props = {
  images: EntityImage[];
};

export function ChatGeneratedImages({ images }: Props) {
  const ready = images.filter((img) => img.url?.trim());
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    globalThis.addEventListener("keydown", onKey);
    return () => globalThis.removeEventListener("keydown", onKey);
  }, [lightbox]);

  if (!ready.length) return null;

  return (
    <>
      <div className="chat-generated-images" aria-label="Сгенерированное изображение">
        {ready.map((img) => (
          <button
            key={img.url}
            type="button"
            className="chat-generated-image-item"
            onClick={() =>
              setLightbox({ url: img.url, title: img.title || "Сгенерированное изображение" })
            }
          >
            <img src={img.url} alt={img.title || ""} referrerPolicy="no-referrer" decoding="async" />
          </button>
        ))}
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
            aria-label={lightbox.title}
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
          </div>
        </div>
      )}
    </>
  );
}
