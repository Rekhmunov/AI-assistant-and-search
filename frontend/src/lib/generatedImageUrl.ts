const GENERATED_FILE_URL_RE = /\/api\/files\/([0-9a-f-]{36})\/content/i;

/** URL сгенерированных картинок Glosix (не веб-поиск). */
export function isGeneratedImageUrl(url: string): boolean {
  const u = (url || "").trim();
  if (!u) return false;
  return GENERATED_FILE_URL_RE.test(u);
}

export function parseGeneratedFileId(url: string): string | null {
  const u = (url || "").trim();
  const match = GENERATED_FILE_URL_RE.exec(u);
  return match?.[1] ?? null;
}

/** Показывать полноразмерный блок в чате, а не карусель поиска. */
export function useChatGeneratedImageLayout(
  turn: Pick<ThreadTurnLike, "isImageGen" | "images" | "sources" | "needsSearch">,
): boolean {
  if (turn.isImageGen === true) return true;
  if (turn.images?.some((img) => isGeneratedImageUrl(img.url))) return true;
  if (
    (turn.images?.length ?? 0) >= 1 &&
    !(turn.sources?.length ?? 0) &&
    turn.needsSearch === false
  ) {
    return turn.images!.every((img) => !isExternalSearchImageUrl(img.url));
  }
  return false;
}

type ThreadTurnLike = {
  isImageGen?: boolean;
  images?: { url: string }[];
  sources?: unknown[];
  needsSearch?: boolean;
};

/** Картинки с Яндекса / внешних CDN — карусель поиска. */
function isExternalSearchImageUrl(url: string): boolean {
  const u = url.toLowerCase();
  if (isGeneratedImageUrl(url)) return false;
  return u.startsWith("http://") || u.startsWith("https://");
}
