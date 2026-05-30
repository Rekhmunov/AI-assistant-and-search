/** Склонение «N источник / источника / источников». */
export function sourcesCountLabel(count: number): { count: string; word: string } {
  const n = Math.max(0, Math.floor(count));
  const mod10 = n % 10;
  const mod100 = n % 100;
  let word = "источников";
  if (mod100 < 11 || mod100 > 14) {
    if (mod10 === 1) word = "источник";
    else if (mod10 >= 2 && mod10 <= 4) word = "источника";
  }
  return { count: String(n), word };
}
