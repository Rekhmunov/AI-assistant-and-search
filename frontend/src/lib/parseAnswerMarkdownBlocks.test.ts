import { describe, expect, it } from "vitest";
import { parseAnswerMarkdownBlocks } from "./parseAnswerMarkdownBlocks";

describe("parseAnswerMarkdownBlocks", () => {
  it("parses markdown headings as heading blocks", () => {
    const blocks = parseAnswerMarkdownBlocks("## Краткий ответ\n\nТекст абзаца.");
    expect(blocks).toEqual([
      { type: "heading", text: "Краткий ответ" },
      { type: "paragraph", text: "Текст абзаца." },
    ]);
  });

  it("parses unordered lists", () => {
    const blocks = parseAnswerMarkdownBlocks("- первый\n- второй");
    expect(blocks).toEqual([
      { type: "ul", items: ["первый", "второй"] },
    ]);
  });

  it("parses ordered lists", () => {
    const blocks = parseAnswerMarkdownBlocks("1. шаг один\n2. шаг два");
    expect(blocks).toEqual([
      { type: "ol", items: ["шаг один", "шаг два"] },
    ]);
  });

  it("treats bold-only line as heading", () => {
    const blocks = parseAnswerMarkdownBlocks("**Итог**\n\nОбычный текст.");
    expect(blocks[0]).toEqual({ type: "heading", text: "Итог" });
  });
});
