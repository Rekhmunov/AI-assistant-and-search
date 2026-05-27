import { describe, expect, it } from "vitest";
import { moveCitationsToParagraphEnds } from "./moveCitationsToParagraphEnds";

describe("moveCitationsToParagraphEnds", () => {
  it("moves citations to paragraph end", () => {
    const input = "Курс доллара [1] вырос на фоне [2] новостей.";
    expect(moveCitationsToParagraphEnds(input)).toBe(
      "Курс доллара вырос на фоне новостей [1][2].",
    );
  });

  it("keeps paragraphs separate", () => {
    const input = "Абзац [1] один.\n\nВторой [2] текст.";
    expect(moveCitationsToParagraphEnds(input)).toBe(
      "Абзац один [1].\n\nВторой текст [2].",
    );
  });
});
