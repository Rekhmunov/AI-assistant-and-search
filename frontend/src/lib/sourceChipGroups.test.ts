import { describe, expect, it } from "vitest";
import { groupSourcesForChips } from "./sourceChipGroups";
import type { Source } from "../api/client";

describe("groupSourcesForChips", () => {
  it("groups duplicate domains with +N suffix count", () => {
    const sources: Source[] = [
      {
        index: 1,
        url: "https://youtube.com/a",
        title: "A",
        snippet: "",
        domain: "youtube.com",
      },
      {
        index: 2,
        url: "https://youtube.com/b",
        title: "B",
        snippet: "",
        domain: "youtube.com",
      },
      {
        index: 3,
        url: "https://rbc.ru/x",
        title: "C",
        snippet: "",
        domain: "rbc.ru",
      },
    ];

    const groups = groupSourcesForChips([1, 2, 3], sources);
    expect(groups).toHaveLength(2);
    expect(groups.find((g) => g.label === "youtube")?.extraCount).toBe(1);
    expect(groups.find((g) => g.label === "rbc")?.extraCount).toBe(0);
  });
});
