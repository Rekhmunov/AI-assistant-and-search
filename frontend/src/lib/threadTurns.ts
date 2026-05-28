import type { Message, MessageFeedback, Source } from "../api/client";

export type ThreadTurn = {
  key: string;
  query: string;
  answer: string;
  sources: Source[];
  followUps: string[];
  userFeedback?: MessageFeedback | null;
  streaming?: boolean;
};

/** Собирает пары вопрос–ответ из сообщений API (по порядку created_at). */
export function messagesToTurns(messages: Message[]): ThreadTurn[] {
  const sorted = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
  const turns: ThreadTurn[] = [];
  let pendingUser: Message | null = null;

  for (const m of sorted) {
    if (m.role === "user") {
      pendingUser = m;
    } else if (m.role === "assistant" && pendingUser) {
      turns.push({
        key: m.id,
        query: pendingUser.content,
        answer: m.content,
        sources: m.sources ?? [],
        followUps: m.follow_up_questions ?? [],
        userFeedback: m.user_feedback ?? null,
      });
      pendingUser = null;
    }
  }

  if (pendingUser) {
    turns.push({
      key: pendingUser.id,
      query: pendingUser.content,
      answer: "",
      sources: [],
      followUps: [],
    });
  }

  return turns;
}
