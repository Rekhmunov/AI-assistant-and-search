import { useState } from "react";
import type { EntityImage } from "../api/client";
import { ImageLightboxOverlay } from "./ImageLightboxOverlay";
import { ProtectedGeneratedImage } from "./ProtectedGeneratedImage";

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
          <ProtectedGeneratedImage
            key={img.url}
            image={img}
            className="chat-generated-image-item"
            showDownload
            onClick={() =>
              setLightbox({ url: img.url, title: img.title || "Сгенерированное изображение" })
            }
          />
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
