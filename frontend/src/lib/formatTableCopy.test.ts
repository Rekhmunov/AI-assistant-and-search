import { describe, expect, it } from "vitest";
import { formatTableForCopy } from "./formatTableCopy";

describe("formatTableForCopy", () => {
  it("formats header and rows as markdown table", () => {
    const text = formatTableForCopy(
      ["Функция", "MAX"],
      [
        ["ИИ", "Да [1]"],
        ["Шифрование", "Нет"],
      ],
    );
    expect(text).toBe(
      [
        "| Функция | MAX |",
        "| --- | --- |",
        "| ИИ | Да |",
        "| Шифрование | Нет |",
      ].join("\n"),
    );
  });

  it("pads short rows to header width", () => {
    const text = formatTableForCopy(["A", "B", "C"], [["1", "2"]]);
    expect(text).toContain("| A | B | C |");
    expect(text).toContain("| 1 | 2 |  |");
  });
});
