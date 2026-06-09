import { describe, expect, it } from "vitest";
import { resolveUnifiedDocument } from "./resolveUnifiedDocument";

describe("resolveUnifiedDocument", () => {
  it("merges markdown attachment with chart in answer", () => {
    const answer = [
      "Вот обновлённый документ.",
      "",
      "```chart",
      '{"type":"bar","title":"T","labels":["A"],"series":[{"name":"S","values":[1]}]}',
      "```",
      "",
      "Краткий итог в конце.",
    ].join("\n");
    const unified = resolveUnifiedDocument(answer, {
      title: "Документ",
      content: "# Документ\n\nОсновной текст.",
      collapsible: false,
    });
    expect(unified).not.toBeNull();
    expect(unified?.markdownParts[0]).toContain("# Документ");
    expect(unified?.charts).toHaveLength(1);
  });
});
