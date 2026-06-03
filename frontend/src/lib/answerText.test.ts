import { describe, expect, it } from "vitest";
import { answerHasText, normalizeAnswerText } from "./answerText";

describe("normalizeAnswerText", () => {
  it("keeps strings", () => {
    expect(normalizeAnswerText(" hello ")).toBe(" hello ");
  });

  it("coerces nullish to empty", () => {
    expect(normalizeAnswerText(null)).toBe("");
    expect(normalizeAnswerText(undefined)).toBe("");
  });

  it("drops objects (avoids trim crash)", () => {
    expect(normalizeAnswerText([{ msg: "too long" }])).toBe("");
  });
});

describe("answerHasText", () => {
  it("detects non-empty trimmed text", () => {
    expect(answerHasText("x")).toBe(true);
    expect(answerHasText("   ")).toBe(false);
  });
});
