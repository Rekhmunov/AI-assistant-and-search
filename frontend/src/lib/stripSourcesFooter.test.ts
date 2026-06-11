import { describe, expect, it } from "vitest";
import { displayAnswerText, stripSourcesFooter } from "./stripSourcesFooter";

describe("stripSourcesFooter", () => {
  it("removes trailing sources block", () => {
    const raw =
      "Курс USD/RUB: 92,5 ₽\n\nИсточники:\n[1] ЦБ РФ — https://cbr.ru\n[2] Investing — https://investing.com";
    expect(stripSourcesFooter(raw)).toBe("Курс USD/RUB: 92,5 ₽");
  });

  it("keeps body when no footer", () => {
    expect(stripSourcesFooter("Ответ с цитатой [1] в тексте.")).toBe("Ответ с цитатой [1] в тексте.");
  });
});

describe("displayAnswerText", () => {
  it("strips footer only when structured sources exist", () => {
    const raw = "Текст\n\nИсточники:\n[1] Example — https://ex.com";
    expect(displayAnswerText(raw, [])).toBe(raw);
    expect(displayAnswerText(raw, [{ index: 1, url: "https://ex.com", title: "Ex", snippet: "", domain: "ex.com" }])).toBe(
      "Текст",
    );
  });
});
