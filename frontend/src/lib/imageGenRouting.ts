/**
 * Frontend-детекция генерации картинок отключена.
 * Маршрутизация полностью на стороне LLM-роутера (backend).
 * Возвращает false всегда — сервер сам определяет image_generate через LLM.
 */
export function wantsImageGeneration(_query: string): boolean {
  return false;
}
