/** Детекция запроса на генерацию картинки (синхронно с backend image_gen_routing). */

const IMAGE_GEN_RE =
  /(?:нарисуй|нарисовать|рисуй|рисунок|сгенерируй|сгенерировать|генерируй|генерация|создай|создать|сделай|сделать|нарисуйте|сгенерируйте|создайте|сделайте)(?:\s+(?:мне|пожалуйста|pls|please))?\s+(?:картинк|изображен|иллюстрац|фото|рисун|арт|шедевр|png|логотип)/i;

const IMAGE_GEN_SHORT_RE =
  /^(?:(?:нарисуй|сгенерируй|создай|сделай|рисуй)\s+.{3,}|(?:картинка|изображение|иллюстрация|арт)\s*[:—-]\s*.+)$/i;

export function wantsImageGeneration(query: string): boolean {
  const text = (query || "").trim();
  if (text.length < 4) return false;
  if (IMAGE_GEN_SHORT_RE.test(text)) return true;
  return IMAGE_GEN_RE.test(text);
}
