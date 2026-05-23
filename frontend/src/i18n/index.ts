import ru from "./ru.json";

const dict = ru;

export function t(key: keyof typeof ru): string {
  return dict[key] ?? key;
}
