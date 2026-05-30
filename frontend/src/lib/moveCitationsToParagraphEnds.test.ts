import { describe, expect, it } from "vitest";
import { moveCitationsToParagraphEnds } from "./moveCitationsToParagraphEnds";
import { sourceDomainLabel } from "./sourceDomainLabel";

describe("sourceDomainLabel", () => {
  it("strips www and TLD", () => {
    expect(sourceDomainLabel("www.rbc.ru")).toBe("rbc");
    expect(sourceDomainLabel("youtube.com")).toBe("youtube");
    expect(sourceDomainLabel("https://www.gazeta.ru/path")).toBe("gazeta");
  });
});

describe("moveCitationsToParagraphEnds", () => {
  it("removes citation markers from paragraph text", () => {
    const input = "Курс доллара [1] вырос на фоне [2] новостей.";
    expect(moveCitationsToParagraphEnds(input)).toBe(
      "Курс доллара вырос на фоне новостей.",
    );
  });

  it("keeps paragraphs separate", () => {
    const input = "Абзац [1] один.\n\nВторой [2] текст.";
    expect(moveCitationsToParagraphEnds(input)).toBe("Абзац один.\n\nВторой текст.");
  });
});
