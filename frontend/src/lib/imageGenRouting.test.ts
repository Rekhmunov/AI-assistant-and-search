import { describe, expect, it } from "vitest";
import { wantsImageGeneration } from "./imageGenRouting";

describe("wantsImageGeneration", () => {
  it("detects generate photo phrasing", () => {
    expect(wantsImageGeneration("Сгенерируй фото кота")).toBe(true);
    expect(wantsImageGeneration("Нарисуй розового кота")).toBe(true);
  });

  it("ignores regular search", () => {
    expect(wantsImageGeneration("Курс доллара")).toBe(false);
  });
});
