import { describe, expect, it } from "vitest";
import type { SupportTicketUser } from "../api/client";
import { sortSupportTickets } from "./supportTicketsSort";

function ticket(id: string, status: string, created_at: string): SupportTicketUser {
  return {
    id,
    source: "general",
    message: "msg",
    status,
    created_at,
    closed_at: null,
    has_unread_reply: false,
    can_reply: status !== "closed",
    replies: [],
  };
}

describe("sortSupportTickets", () => {
  it("puts active tickets before closed, newest first within each group", () => {
    const sorted = sortSupportTickets([
      ticket("c-old", "closed", "2026-01-01T10:00:00Z"),
      ticket("o-old", "open", "2026-01-02T10:00:00Z"),
      ticket("c-new", "closed", "2026-01-05T10:00:00Z"),
      ticket("p-new", "in_progress", "2026-01-04T10:00:00Z"),
      ticket("o-new", "open", "2026-01-03T10:00:00Z"),
    ]);
    expect(sorted.map((t) => t.id)).toEqual([
      "o-new",
      "p-new",
      "o-old",
      "c-new",
      "c-old",
    ]);
  });
});
