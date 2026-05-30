import { describe, expect, it } from "vitest";
import { mergeThreadTurns, type ThreadTurn } from "./threadTurns";

describe("mergeThreadTurns", () => {
  it("preserves local followUps when API message has none yet", () => {
    const local: ThreadTurn[] = [
      {
        key: "stream-1",
        messageId: "msg-1",
        query: "питбуль",
        answer: "Ответ",
        sources: [],
        images: [],
        followUps: ["История породы", "Дрессировка питбуля", "Питание щенка"],
      },
    ];
    const api: ThreadTurn[] = [
      {
        key: "msg-1",
        query: "питбуль",
        answer: "Ответ",
        sources: [],
        images: [],
        followUps: [],
      },
    ];

    const merged = mergeThreadTurns(local, api);
    expect(merged).toHaveLength(1);
    expect(merged[0].followUps).toEqual([
      "История породы",
      "Дрессировка питбуля",
      "Питание щенка",
    ]);
  });
});
