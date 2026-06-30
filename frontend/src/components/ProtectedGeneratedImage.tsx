import { useCallback } from "react";
import { ArrowDownToLine } from "lucide-react";
import type { EntityImage } from "../api/client";
import { useProtectedImageSrc } from "../hooks/useProtectedImageSrc";
import { isGeneratedImageUrl } from "../lib/generatedImageUrl";

type Props = {
  image: EntityImage;
  className?: string;
  loading?: "lazy" | "eager" | undefined;
  onClick?: () => void;
  /** Показывать кнопку скачивания в правом верхнем углу. */
  showDownload?: boolean;
};

export function ProtectedGeneratedImage({ image, className, loading = "lazy", onClick, showDownload }: Props) {
  const directUrl = isGeneratedImageUrl(image.url) ? undefined : image.url?.trim();
  const src = useProtectedImageSrc(image.url) ?? directUrl;

  const handleDownload = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!src) return;

      const raw = (image.title || "generated-image").trim();
      const safe = raw.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").slice(0, 80) || "image";
      const filename = safe.endsWith(".jpg") || safe.endsWith(".png") ? safe : `${safe}.jpg`;

      // src уже является blob URL (из useProtectedImageSrc) — используем напрямую.
      // Если по какой-то причине это не blob URL — фетчим и создаём blob.
      let downloadUrl = src;
      let blobCreated = false;
      if (!src.startsWith("blob:")) {
        try {
          const resp = await fetch(src);
          const blob = await resp.blob();
          downloadUrl = URL.createObjectURL(blob);
          blobCreated = true;
        } catch { return; }
      }

      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      if (blobCreated) setTimeout(() => URL.revokeObjectURL(downloadUrl), 10_000);
    },
    [src, image.title],
  );

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

  const downloadBtn =
    showDownload && src ? (
      <button
        type="button"
        className="generated-image-download-btn"
        onClick={handleDownload}
        aria-label="Скачать изображение"
        title="Скачать"
      >
        <ArrowDownToLine width={15} height={15} strokeWidth={2} aria-hidden />
      </button>
    ) : null;

  if (onClick) {
    return (
      <button type="button" className={className} onClick={onClick}>
        {img}
        {downloadBtn}
      </button>
    );
  }

  return (
    <div className={className}>
      {img}
      {downloadBtn}
    </div>
  );
}
