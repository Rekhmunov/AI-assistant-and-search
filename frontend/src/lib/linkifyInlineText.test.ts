import { describe, expect, it } from "vitest";
import { linkifyPlainText, splitBareUrls, splitMarkdownLinks } from "./linkifyInlineText";

describe("splitMarkdownLinks", () => {
  it("extracts markdown link label and href", () => {
    const parts = splitMarkdownLinks("Сайт: [официальный](https://example.com/path) здесь");
    expect(parts).toEqual([
      { type: "text", value: "Сайт: " },
      { type: "link", label: "официальный", href: "https://example.com/path" },
      { type: "text", value: " здесь" },
    ]);
  });
});

describe("splitBareUrls", () => {
  it("extracts bare url and keeps trailing punctuation outside", () => {
    const parts = splitBareUrls("Перейдите на https://example.com.");
    expect(parts).toEqual([
      { type: "text", value: "Перейдите на " },
      { type: "link", label: "https://example.com", href: "https://example.com" },
      { type: "text", value: "." },
    ]);
  });
});

describe("linkifyPlainText", () => {
  it("handles markdown links and bare urls together", () => {
    const parts = linkifyPlainText("A [B](https://b.test) C https://c.test");
    expect(parts).toEqual([
      { type: "text", value: "A " },
      { type: "link", label: "B", href: "https://b.test" },
      { type: "text", value: " C " },
      { type: "link", label: "https://c.test", href: "https://c.test" },
    ]);
  });

  it("linkifies domain paths without scheme", () => {
    const parts = linkifyPlainText("Бот: max.ru/mfcryazan_bot");
    expect(parts).toEqual([
      { type: "text", value: "Бот: " },
      { type: "link", label: "max.ru/mfcryazan_bot", href: "max.ru/mfcryazan_bot" },
    ]);
  });
});
