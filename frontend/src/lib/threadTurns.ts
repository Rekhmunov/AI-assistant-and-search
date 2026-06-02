import type { Message, MessageFeedback, Source, EntityImage } from "../api/client";

export type ThreadTurn = {
  key: string;
  /** UUID сообщения ассистента после done — для футера до смены key */
  messageId?: string;
  query: string;
  answer: string;
  sources: Source[];
  images: EntityImage[];
  followUps: string[];
  needsSearch?: boolean;
  /** Генерация изображения (GigaChat text2image), не веб-поиск */
  isImageGen?: boolean;
  userFeedback?: MessageFeedback | null;
  streaming?: boolean;
  errorCode?: string;
};

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** UUID assistant message for feedback footer — from messageId or stable turn key. */
export function resolveAssistantMessageId(
  turn: Pick<ThreadTurn, "key" | "messageId">,
): string | undefined {
  const candidate = turn.messageId ?? turn.key;
  return UUID_RE.test(candidate) ? candidate : undefined;
}

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
        messageId: m.id,
        query: pendingUser.content,
        answer: m.content,
        sources: m.sources ?? [],
        images: m.images ?? [],
        followUps: (m.follow_up_questions ?? []).slice(0, 3),
        needsSearch: (m.sources?.length ?? 0) > 0 || (m.images?.length ?? 0) > 0,
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
      images: [],
      followUps: [],
    });
  }

  return turns;
}

/** Не затираем локальный ответ/фото, если API ещё не сохранил assistant message. */
export function mergeThreadTurns(local: ThreadTurn[], api: ThreadTurn[]): ThreadTurn[] {
  if (local.length === 0) return api;
  if (api.length === 0) return local;

  const localByKey = new Map(local.map((turn) => [turn.key, turn]));

  const preserveLocalMedia = (turns: ThreadTurn[]): ThreadTurn[] =>
    turns.map((turn) => {
      const prev = localByKey.get(turn.key);
      if (!prev) return turn;
      return {
        ...turn,
        images: turn.images?.length ? turn.images : prev.images,
        sources: turn.sources?.length ? turn.sources : prev.sources,
      };
    });

  const lastLocal = local[local.length - 1];
  const lastApi = api[api.length - 1];

  if (lastLocal.messageId) {
    const match = api.find((t) => t.key === lastLocal.messageId);
    if (match?.answer.trim()) {
      if (lastLocal.followUps.length > 0 && match.followUps.length === 0) {
        return preserveLocalMedia(
          api.map((t) =>
            t.key === lastLocal.messageId ? { ...t, followUps: lastLocal.followUps } : t,
          ),
        );
      }
      return preserveLocalMedia(api);
    }
  }

  if (
    lastLocal.query === lastApi.query &&
    !lastApi.answer.trim() &&
    (lastLocal.answer.trim() || lastLocal.images.length > 0)
  ) {
    return preserveLocalMedia([
      ...api.slice(0, -1),
      {
        ...lastLocal,
        key: lastLocal.messageId ?? lastLocal.key,
        streaming: false,
      },
    ]);
  }

  return preserveLocalMedia(api);
}
