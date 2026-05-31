import { describe, expect, it } from "vitest";
import { mergeCitationIndices, parseParagraphCitations } from "./paragraphCitations";

describe("parseParagraphCitations", () => {
  it("extracts source indices and removes markers from text", () => {
    const result = parseParagraphCitations("Текст про породу [1] и характер [2].");
    expect(result.text).toBe("Текст про породу и характер.");
    expect(result.indices).toEqual([1, 2]);
  });
});

describe("mergeCitationIndices", () => {
  it("merges without duplicates preserving order", () => {
    expect(mergeCitationIndices([1, 2], [2, 3], [1])).toEqual([1, 2, 3]);
  });
});
