import { describe, expect, it } from "vitest";
import { parseAnswerSegments } from "./parseAnswerSegments";

describe("parseAnswerSegments", () => {
  it("skips empty fenced block after markdown document", () => {
    const raw = [
      "Вот документ.",
      "",
      "```markdown",
      "# Заголовок",
      "Текст документа.",
      "```",
      "",
      "```",
      "```",
    ].join("\n");
    const segments = parseAnswerSegments(raw);
    const codeBlocks = segments.filter((s) => s.type === "code");
    expect(codeBlocks).toHaveLength(1);
    expect(codeBlocks[0].lang).toBe("markdown");
  });
});
