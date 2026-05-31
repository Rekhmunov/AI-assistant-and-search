import { describe, expect, it } from "vitest";
import { parseAnswerMarkdownBlocks } from "./parseAnswerMarkdownBlocks";

describe("parseAnswerMarkdownBlocks", () => {
  it("treats single numbered line as heading without number prefix", () => {
    const blocks = parseAnswerMarkdownBlocks("1. Официальный курс ЦБ\n\nТекст абзаца.");
    expect(blocks[0]).toEqual({ type: "heading", text: "Официальный курс ЦБ" });
  });

  it("keeps real ordered lists when numbers continue", () => {
    const blocks = parseAnswerMarkdownBlocks("1. шаг один\n2. шаг два");
    expect(blocks[0]).toEqual({ type: "ol", items: ["шаг один", "шаг два"] });
  });

  it("strips leading number from markdown headings", () => {
    const blocks = parseAnswerMarkdownBlocks("## 1. Заголовок");
    expect(blocks[0]).toEqual({ type: "heading", text: "Заголовок" });
  });
});
