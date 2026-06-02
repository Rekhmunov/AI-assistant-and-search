import { useState } from "react";
import type { EntityImage } from "../api/client";
import { ImageLightboxOverlay } from "./ImageLightboxOverlay";

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
        <ImageLightboxOverlay
          url={lightbox.url}
          title={lightbox.title}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}
