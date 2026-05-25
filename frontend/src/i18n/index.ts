import ru from "./ru.json";

const dict = ru;

export function t(key: keyof typeof ru, vars?: Record<string, string | number>): string {
  let s = dict[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replace(`{${k}}`, String(v));
    }
  }
  return s;
}
