import { describe, expect, it } from "vitest";
import {
  mergeThreadTurns,
  messagesToTurns,
  resolveAssistantMessageId,
  type ThreadTurn,
} from "./threadTurns";

const ASSISTANT_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

describe("resolveAssistantMessageId", () => {
  it("uses messageId when set", () => {
    expect(
      resolveAssistantMessageId({
        key: "stream-123",
        messageId: ASSISTANT_ID,
      }),
    ).toBe(ASSISTANT_ID);
  });

  it("falls back to turn key for synced API turns", () => {
    expect(
      resolveAssistantMessageId({
        key: ASSISTANT_ID,
      }),
    ).toBe(ASSISTANT_ID);
  });

  it("ignores non-uuid stream keys", () => {
    expect(
      resolveAssistantMessageId({
        key: "stream-123",
      }),
    ).toBeUndefined();
  });
});

describe("messagesToTurns", () => {
  it("sets messageId on assistant turns", () => {
    const turns = messagesToTurns([
      {
        id: "user-1",
        role: "user",
        content: "вопрос",
        created_at: "2026-01-01T10:00:00Z",
        sources: null,
        images: null,
        follow_up_questions: null,
        user_feedback: null,
      },
      {
        id: ASSISTANT_ID,
        role: "assistant",
        content: "ответ",
        created_at: "2026-01-01T10:00:01Z",
        sources: null,
        images: null,
        follow_up_questions: ["ещё"],
        user_feedback: null,
      },
    ]);
    expect(turns).toHaveLength(1);
    expect(turns[0].key).toBe(ASSISTANT_ID);
    expect(turns[0].messageId).toBe(ASSISTANT_ID);
  });
});

describe("mergeThreadTurns", () => {
  it("preserves local followUps when API message has none yet", () => {
    const local: ThreadTurn[] = [
      {
        key: "stream-1",
        messageId: "msg-1",
        query: "питбуль",
        attachments: [],
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
        attachments: [],
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

  it("preserves local images when API message has none yet", () => {
    const images = [{ url: "https://img/1.jpg", title: "a", page_url: "https://a" }];
    const local: ThreadTurn[] = [
      {
        key: "msg-1",
        messageId: "msg-1",
        query: "Gefu",
        attachments: [],
        answer: "Ответ",
        sources: [],
        images,
        followUps: [],
      },
    ];
    const api: ThreadTurn[] = [
      {
        key: "msg-1",
        query: "Gefu",
        attachments: [],
        answer: "Ответ",
        sources: [],
        images: [],
        followUps: [],
      },
    ];

    const merged = mergeThreadTurns(local, api);
    expect(merged[0].images).toEqual(images);
  });
});
