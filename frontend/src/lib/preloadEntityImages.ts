import type { EntityImage } from "../api/client";

const MIN_SIDE = 80;
const MAX_IMAGES = 12;

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

export async function preloadEntityImages(images: EntityImage[]): Promise<EntityImage[]> {
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
