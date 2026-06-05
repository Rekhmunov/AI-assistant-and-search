import type { EntityImage } from "../api/client";
import { useProtectedImageSrc } from "../hooks/useProtectedImageSrc";
import { isGeneratedImageUrl } from "../lib/generatedImageUrl";

type Props = {
  image: EntityImage;
  className?: string;
  loading?: "lazy" | "eager" | undefined;
  onClick?: () => void;
};

export function ProtectedGeneratedImage({ image, className, loading = "lazy", onClick }: Props) {
  const directUrl = isGeneratedImageUrl(image.url) ? undefined : image.url?.trim();
  const src = useProtectedImageSrc(image.url) ?? directUrl;

  if (!src) {
    return (
      <span className={className} aria-hidden>
        …
      </span>
    );
  }

  const img = (
    <img
      src={src}
      alt={image.title || ""}
      referrerPolicy="no-referrer"
      decoding="async"
      loading={loading}
    />
  );

  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        {img}
      </button>
    );
  }

  return <div className={className}>{img}</div>;
}
