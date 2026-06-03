import { describe, expect, it } from "vitest";
import { stripUserQueryDisplay } from "./userQueryDisplay";

describe("stripUserQueryDisplay", () => {
  it("removes trailing [Файлы: …] marker", () => {
    expect(
      stripUserQueryDisplay("Что на фото?\n\n[Файлы: photo.jpg]"),
    ).toBe("Что на фото?");
  });

  it("keeps plain query unchanged", () => {
    expect(stripUserQueryDisplay("  простой вопрос  ")).toBe("  простой вопрос");
  });
});
