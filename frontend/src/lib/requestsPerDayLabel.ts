/** «1 запрос», «2 запроса», «5 запросов» */
export function requestsPerDayLabel(count: number): string {
  const n = Math.max(0, Math.floor(count));
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} запрос`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} запроса`;
  return `${n} запросов`;
}
