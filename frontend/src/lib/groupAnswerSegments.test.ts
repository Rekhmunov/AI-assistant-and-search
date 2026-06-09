import { describe, expect, it } from "vitest";
import { parseAnswerSegments } from "./parseAnswerSegments";
import { groupAnswerSegments } from "./groupAnswerSegments";

describe("groupAnswerSegments", () => {
  it("merges markdown and chart separated by blank lines", () => {
    const raw = [
      "```markdown",
      "# Документ",
      "Текст.",
      "```",
      "",
      "",
      "```chart",
      '{"type":"bar","title":"T","labels":["A"],"series":[{"name":"S","values":[1]}]}',
      "```",
    ].join("\n");
    const grouped = groupAnswerSegments(parseAnswerSegments(raw));
    expect(grouped.some((s) => s.type === "document")).toBe(true);
  });

  it("merges markdown chart markdown into one document block", () => {
    const raw = [
      "Вот документ с диаграммой.",
      "",
      "```markdown",
      "# YandexGPT 5",
      "Текст раздела.",
      "```",
      "",
      "```chart",
      '{"type":"bar","title":"T","labels":["A"],"series":[{"name":"S","values":[1]}]}',
      "```",
      "",
      "```markdown",
      "## Выводы",
      "Итог.",
      "```",
    ].join("\n");

    const grouped = groupAnswerSegments(parseAnswerSegments(raw));
    expect(grouped.filter((s) => s.type === "document")).toHaveLength(1);
    const doc = grouped.find((s) => s.type === "document");
    expect(doc && doc.type === "document" && doc.markdownParts).toHaveLength(2);
    expect(doc && doc.type === "document" && doc.charts).toHaveLength(1);
  });
});
