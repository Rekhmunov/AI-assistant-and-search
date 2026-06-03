import type { EntityImage } from "../api/client";

const MIN_SIDE = 80;
const MAX_IMAGES = 12;

/** Уже успешно проверенные в этой вкладке — не дергаем сеть повторно при refetch треда. */
const validatedUrlCache = new Set<string>();

function preloadImage(url: string): Promise<boolean> {
  if (validatedUrlCache.has(url)) return Promise.resolve(true);
  return new Promise((resolve) => {
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.decoding = "async";
    img.onload = () => {
      const ok = img.naturalWidth >= MIN_SIDE && img.naturalHeight >= MIN_SIDE;
      if (ok) validatedUrlCache.add(url);
      resolve(ok);
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
