import { describe, expect, it } from "vitest";
import { buildThreadImageGroups, countThreadImages } from "./threadImageGroups";
import type { ThreadTurn } from "./threadTurns";

function turn(partial: Partial<ThreadTurn> & Pick<ThreadTurn, "key" | "query">): ThreadTurn {
  return {
    answer: "",
    sources: [],
    images: [],
    followUps: [],
    ...partial,
  };
}

describe("buildThreadImageGroups", () => {
  it("returns newest turn groups first", () => {
    const groups = buildThreadImageGroups([
      turn({
        key: "1",
        query: "Первый вопрос",
        images: [{ url: "https://a/1.jpg", title: "a", page_url: "https://a" }],
      }),
      turn({
        key: "2",
        query: "Второй вопрос",
        images: [{ url: "https://b/1.jpg", title: "b", page_url: "https://b" }],
      }),
    ]);

    expect(groups.map((g) => g.query)).toEqual(["Второй вопрос", "Первый вопрос"]);
  });

  it("counts all images in thread", () => {
    const total = countThreadImages([
      turn({ key: "1", query: "a", images: [{ url: "u1", title: "", page_url: "p1" }] }),
      turn({
        key: "2",
        query: "b",
        images: [
          { url: "u2", title: "", page_url: "p2" },
          { url: "u3", title: "", page_url: "p3" },
        ],
      }),
    ]);
    expect(total).toBe(3);
  });
});
