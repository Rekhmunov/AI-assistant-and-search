/** URL сгенерированных картинок Glosix (не веб-поиск). */
export function isGeneratedImageUrl(url: string): boolean {
  return /\/api\/files\/[0-9a-f-]{36}\/content/i.test(url);
}
