import { describe, expect, it } from "vitest";
import { hasMaxWebAppHashInUrl } from "./maxApp";

describe("hasMaxWebAppHashInUrl", () => {
  it("detects MAX WebApp hash fragments", () => {
    const sample =
      "https://glosix.ru/#WebAppData=user%3D%7B%22id%22:1%7D&WebAppPlatform=android&WebAppVersion=26.18.2";
    expect(hasMaxWebAppHashInUrl(sample)).toBe(true);
  });

  it("ignores regular SPA routes", () => {
    expect(hasMaxWebAppHashInUrl("https://glosix.ru/")).toBe(false);
    expect(hasMaxWebAppHashInUrl("https://glosix.ru/thread/abc")).toBe(false);
  });
});
