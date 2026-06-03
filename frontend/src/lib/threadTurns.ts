import type {
  Message,
  MessageAttachment,
  MessageFeedback,
  MarkdownDocumentInfo,
  Source,
  EntityImage,
} from "../api/client";
import { stripUserQueryDisplay } from "./userQueryDisplay";

export type ThreadTurn = {
  key: string;
  /** UUID сообщения ассистента после done — для футера до смены key */
  messageId?: string;
  query: string;
  attachments: MessageAttachment[];
  answer: string;
  sources: Source[];
  images: EntityImage[];
  followUps: string[];
  needsSearch?: boolean;
  /** Генерация изображения (GigaChat text2image), не веб-поиск */
  isImageGen?: boolean;
  /** Генерация Word-документа */
  isDocumentGen?: boolean;
  userFeedback?: MessageFeedback | null;
  /** Сгенерированный .docx на ответе ассистента */
  generatedDocument?: MessageAttachment | null;
  /** Markdown-документ в чате (оферта и т.п.) */
  markdownDocument?: MarkdownDocumentInfo | null;
  streaming?: boolean;
  errorCode?: string;
};

function normalizeMessageAttachments(
  raw: Message["attachments"] | undefined,
): MessageAttachment[] {
  if (!raw?.length) return [];
  return raw.map((a) => ({
    id: a.id,
    filename: a.filename,
    kind:
      a.kind === "image"
        ? "image"
        : a.kind === "markdown_document"
          ? "markdown_document"
          : "document",
    url: a.url ?? undefined,
    previewUrl: a.previewUrl,
    share_url: a.share_url ?? undefined,
    ttl_hours: a.ttl_hours ?? undefined,
    title: a.title ?? undefined,
    content: a.content ?? undefined,
  }));
}

function pickGeneratedDocument(raw: Message["attachments"] | undefined): MessageAttachment | null {
  const items = normalizeMessageAttachments(raw);
  const doc = items.find((a) => a.kind === "document" && (a.url || a.share_url));
  return doc ?? null;
}

function pickMarkdownDocument(raw: Message["attachments"] | undefined): MarkdownDocumentInfo | null {
  const items = normalizeMessageAttachments(raw);
  const md = items.find((a) => a.kind === "markdown_document" && a.content);
  if (!md?.content) return null;
  return {
    title: md.title || md.filename || "Документ",
    content: md.content,
    collapsible: md.content.length > 1200,
  };
}

/** После refetch API-URL важнее отозванного blob previewUrl. */
function mergeTurnAttachments(
  api: MessageAttachment[],
  local: MessageAttachment[] | undefined,
): MessageAttachment[] {
  if (!api.length) return local ?? [];
  if (!local?.length) return api;
  return api.map((item) => {
    const prev = local.find((p) => p.id === item.id);
    const url = item.url || prev?.url;
    const previewUrl = url ? undefined : prev?.previewUrl;
    return { ...item, url, previewUrl };
  });
}

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
        query: stripUserQueryDisplay(pendingUser.content),
        attachments: normalizeMessageAttachments(pendingUser.attachments),
        answer: m.content,
        sources: m.sources ?? [],
        images: m.images ?? [],
        followUps: (m.follow_up_questions ?? []).slice(0, 3),
        needsSearch: (m.sources?.length ?? 0) > 0 || (m.images?.length ?? 0) > 0,
        userFeedback: m.user_feedback ?? null,
        generatedDocument: pickGeneratedDocument(m.attachments),
        markdownDocument: pickMarkdownDocument(m.attachments),
      });
      pendingUser = null;
    }
  }

  if (pendingUser) {
    turns.push({
      key: pendingUser.id,
      query: stripUserQueryDisplay(pendingUser.content),
      attachments: normalizeMessageAttachments(pendingUser.attachments),
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
        attachments: mergeTurnAttachments(turn.attachments, prev.attachments),
        generatedDocument: turn.generatedDocument ?? prev.generatedDocument,
        markdownDocument: turn.markdownDocument ?? prev.markdownDocument,
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
