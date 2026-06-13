import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  fetchAnswerStatus,
  fetchFileMeta,
  fetchThread,
  fetchSession,
  streamAgentMessage,
  streamSearch,
  type AnswerStatus,
  type GeneratedDocumentInfo,
  type MessageAttachment,
} from "../api/client";
import { AnswerBody } from "../components/AnswerBody";
import { DocumentAnswerBlock } from "../components/DocumentAnswerBlock";
import { AnswerErrorBoundary } from "../components/AnswerErrorBoundary";
import { AnswerFooter } from "../components/AnswerFooter";
import { FreeLimitNotice } from "../components/FreeLimitNotice";
import { GuestLimitNotice } from "../components/GuestLimitNotice";
import { ChatGeneratedImages } from "../components/ChatGeneratedImages";
import { ImageGenProNotice } from "../components/ImageGenProNotice";
import { ImageGenStatusLine } from "../components/ImageGenStatusLine";
import { DocGenStatusLine } from "../components/DocGenStatusLine";
import { AgentActivityLogPanel } from "../components/AgentActivityLogPanel";
import { AgentThinkingPanel } from "../components/AgentThinkingPanel";
import type { AgentThinkingEvent } from "../api/client";
import { CollapsibleMarkdownDocument } from "../components/CollapsibleMarkdownDocument";
import { GeneratedDocumentCard } from "../components/GeneratedDocumentCard";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SearchStatusLine, type SearchPhase } from "../components/SearchStatusLine";
import { ThreadImagesTab } from "../components/ThreadImagesTab";
import { ThreadMobileHeader } from "../components/ThreadMobileHeader";
import { ThreadQuery } from "../components/ThreadQuery";
import { ThreadTabsBar, type ThreadTab } from "../components/ThreadTabsBar";
import { TurnImageGallery } from "../components/TurnImageGallery";
import { t } from "../i18n";
import { findLastIndex } from "../lib/arrayUtils";
import { useChatGeneratedImageLayout } from "../lib/generatedImageUrl";
import { wantsImageGeneration } from "../lib/imageGenRouting";
import {
  buildThreadImageGroups,
  countThreadImages,
  threadHasSearchTurns,
} from "../lib/threadImageGroups";
import { answerHasText, normalizeAnswerText } from "../lib/answerText";
import { displayAnswerText } from "../lib/stripSourcesFooter";
import { renderAnswerTextSegment } from "../lib/renderAnswerText";
import { resolveUnifiedDocument } from "../lib/resolveUnifiedDocument";
import { SEARCH_QUERY_MAX_LENGTH } from "../lib/searchQueryLimits";
import {
  assistantMessageIdFromThread,
  mergeThreadTurns,
  messagesToTurns,
  resolveAssistantMessageId,
  threadHasPendingAnswer,
  type ThreadTurn,
} from "../lib/threadTurns";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useAuthStore } from "../store/authStore";

function updateLastStreamingTurn(
  turns: ThreadTurn[],
  patch: Partial<
    Pick<
      ThreadTurn,
      | "answer"
      | "sources"
      | "images"
      | "followUps"
      | "needsSearch"
      | "isImageGen"
      | "isDocumentGen"
      | "generatedDocument"
      | "markdownDocument"
    >
  >,
  appendAnswer?: string,
): ThreadTurn[] {
  const idx = findLastIndex(turns, (turn) => turn.streaming);
  if (idx < 0) return turns;
  const current = turns[idx];
  const next = [...turns];
  next[idx] = {
    ...current,
    ...patch,
    answer:
      appendAnswer !== undefined
        ? normalizeAnswerText(current.answer) + normalizeAnswerText(appendAnswer)
        : patch.answer !== undefined
          ? normalizeAnswerText(patch.answer)
          : normalizeAnswerText(current.answer),
  };
  return next;
}

/** follow_ups приходят после done — streaming уже false, нужен последний завершённый turn. */
function updateLastActiveTurn(
  turns: ThreadTurn[],
  patch: Partial<Pick<ThreadTurn, "followUps">>,
): ThreadTurn[] {
  const idx = findLastIndex(
    turns,
    (turn) => turn.streaming || Boolean(turn.messageId) || answerHasText(turn.answer),
  );
  if (idx < 0) return turns;
  const next = [...turns];
  next[idx] = { ...next[idx], ...patch };
  return next;
}

type ThreadLocationState = {
  fromHistory?: boolean;
  pendingAttachments?: MessageAttachment[];
  agentRevealWelcome?: boolean;
};

const PENDING_ANSWER_POLL_MS = 4000;
const PENDING_ANSWER_POLL_MAX_MS = 10 * 60 * 1000;
const AUTO_RESUME_GRACE_MS = 1500;
const AUTO_RESUME_MAX_ATTEMPTS = 3;
/** Если active слишком долго — принудительно возобновляем (зависший Redis pending). */
const PENDING_ACTIVE_FORCE_RESUME_SEC = 8;

function answerStatusPhaseToSearchPhase(
  phase: string | null | undefined,
  needsSearch?: boolean | null,
): SearchPhase {
  switch (phase) {
    case "routing":
      return "routing";
    case "searching":
      return "searching";
    case "answering":
      return "answering";
    case "image_generating":
      return "image_generating";
    case "document_generating":
      return "document_generating";
    default:
      return needsSearch ? "searching" : "preparing";
  }
}

function mapComposerAttachments(
  items: { id: string; filename: string; kind: "document" | "image"; previewUrl?: string }[],
): MessageAttachment[] {
  return items.map((a) => ({
    id: a.id,
    filename: a.filename,
    kind: a.kind,
    previewUrl: a.previewUrl,
  }));
}

export function Thread() {
  const { id } = useParams();
  const location = useLocation();
  const fromHistory = Boolean((location.state as ThreadLocationState | null)?.fromHistory);
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const initialFiles = searchParams.get("files")?.split(",").filter(Boolean) ?? [];
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();

  const { data: session } = useQuery({
    queryKey: ["session", token],
    queryFn: () => fetchSession(token),
  });
  const [threadId, setThreadId] = useState<string | null>(id ?? null);
  const [turns, setTurns] = useState<ThreadTurn[]>([]);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [needsSearch, setNeedsSearch] = useState(true);
  const [searchPhase, setSearchPhase] = useState<SearchPhase>("idle");
  const [composerQuery, setComposerQuery] = useState("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [agentStarting, setAgentStarting] = useState(false);
  const [activeTab, setActiveTab] = useState<ThreadTab>("answer");
  const started = useRef(false);
  const pendingPollStartedAtRef = useRef<number | null>(null);
  const autoResumeRef = useRef<{ turnKey: string; attempts: number } | null>(null);
  const autoResumeScheduledRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const isRevealingRef = useRef(false);
  const [lastTurnRevealing, setLastTurnRevealing] = useState(false);
  const activeThreadIdRef = useRef<string | null>(id ?? null);
  const scrollTurnKeyRef = useRef<string | null>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const answerPanelRef = useRef<HTMLDivElement>(null);
  const imagesPanelRef = useRef<HTMLDivElement>(null);
  const answerResetPendingRef = useRef(false);
  const imageGenActiveRef = useRef(false);
  const docGenActiveRef = useRef(false);
  const [docGenStatus, setDocGenStatus] = useState<string | undefined>();
  const [imageGenStatus, setImageGenStatus] = useState<string | undefined>();
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentStatusText, setAgentStatusText] = useState<string | null>(null);
  // Хранит события размышлений по ключу тёрна, чтобы не пропадали при новых запросах
  const [agentThinkingByKey, setAgentThinkingByKey] = useState<Record<string, AgentThinkingEvent[]>>({});
  const currentThinkingKeyRef = useRef<string | null>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const isDesktop = useDesktopLayout();

  const getAnswerScrollEl = useCallback(() => {
    return (isDesktop ? conversationRef.current : answerPanelRef.current) ?? null;
  }, [isDesktop]);

  const scrollAnswerToLastTurn = useCallback(
    (behavior: ScrollBehavior = "auto") => {
      const lastTurn = turns[turns.length - 1];
      if (!lastTurn) return;
      const turnEl = document.getElementById(`turn-${lastTurn.key}`);
      if (turnEl) {
        turnEl.scrollIntoView({ block: "start", behavior });
        return;
      }
      const el = getAnswerScrollEl();
      if (el) el.scrollTo({ top: el.scrollHeight, behavior });
    },
    [turns, getAnswerScrollEl],
  );

  const handleTabChange = useCallback(
    (tab: ThreadTab) => {
      if (tab === activeTab) return;
      setActiveTab(tab);

      if (isDesktop) return;

      requestAnimationFrame(() => {
        if (tab === "images") {
          const el = imagesPanelRef.current;
          if (!el) return;
          el.scrollTop = 0;
          requestAnimationFrame(() => {
            el.scrollTop = 0;
          });
        } else {
          scrollAnswerToLastTurn("auto");
          requestAnimationFrame(() => scrollAnswerToLastTurn("auto"));
        }
      });
    },
    [activeTab, isDesktop, scrollAnswerToLastTurn],
  );

  const activeThreadKey = id ?? threadId;

  const { data: thread } = useQuery({
    queryKey: ["thread", activeThreadKey],
    queryFn: () => fetchThread(token, activeThreadKey!),
    enabled: !!activeThreadKey,
    staleTime: 60_000,
    refetchInterval: (query) => {
      if (streamingRef.current) return false;
      const data = query.state.data;
      if (!data || !threadHasPendingAnswer(data.messages)) {
        pendingPollStartedAtRef.current = null;
        return false;
      }
      if (pendingPollStartedAtRef.current === null) {
        pendingPollStartedAtRef.current = Date.now();
      }
      if (Date.now() - pendingPollStartedAtRef.current > PENDING_ANSWER_POLL_MAX_MS) return false;
      return PENDING_ANSWER_POLL_MS;
    },
  });

  const isAgentThread = thread?.thread_type === "agent";
  const threadHasPending = Boolean(thread && threadHasPendingAnswer(thread.messages));

  const { data: answerStatus } = useQuery({
    queryKey: ["thread-answer-status", activeThreadKey],
    queryFn: () => fetchAnswerStatus(token, activeThreadKey!),
    enabled: !!activeThreadKey && (threadHasPending || agentLoading) && !streaming,
    refetchInterval: (query) => {
      if (streamingRef.current) return false;
      const data = query.state.data;
      if (!data?.pending || data.stale) return false;
      if (pendingPollStartedAtRef.current === null) return PENDING_ANSWER_POLL_MS;
      if (Date.now() - pendingPollStartedAtRef.current > PENDING_ANSWER_POLL_MAX_MS) return false;
      return PENDING_ANSWER_POLL_MS;
    },
  });

  const syncTurnsFromThread = useCallback(() => {
    if (!thread) return;
    const state = location.state as ThreadLocationState | null;
    const revealWelcome = Boolean(state?.agentRevealWelcome);
    setTurns((prev) => {
      const apiTurns = messagesToTurns(thread.messages);
      const prevWelcome = prev.find((t) => t.agentWelcome);
      const shouldStreamWelcome =
        revealWelcome || Boolean(prevWelcome?.streaming && apiTurns[0]?.agentWelcome);
      if (shouldStreamWelcome && apiTurns[0]?.agentWelcome) {
        apiTurns[0] = { ...apiTurns[0], streaming: true };
      }
      return mergeThreadTurns(prev, apiTurns);
    });
    if (revealWelcome) {
      navigate(location.pathname + location.search, {
        replace: true,
        state: { ...(state ?? {}), agentRevealWelcome: false },
      });
    }
  }, [thread, location.pathname, location.search, location.state, navigate]);

  const resolveFeedbackMessageId = useCallback(
    async (threadIdToFetch: string) => {
      try {
        const fresh = await fetchThread(token, threadIdToFetch);
        queryClient.setQueryData(["thread", threadIdToFetch], fresh);
        const assistantId = assistantMessageIdFromThread(fresh.messages);
        if (!assistantId) return;
        setTurns((prev) => {
          const idx = findLastIndex(
            prev,
            (turn) => !turn.streaming && answerHasText(turn.answer) && !resolveAssistantMessageId(turn),
          );
          if (idx < 0) return prev;
          const turn = prev[idx];
          const next = [...prev];
          next[idx] = { ...turn, messageId: assistantId, key: assistantId };
          return next;
        });
      } catch {
        /* ignore */
      }
    },
    [token, queryClient],
  );

  const handleAnswerTypingChange = useCallback(
    (typing: boolean) => {
      isRevealingRef.current = typing;
      setLastTurnRevealing(typing);
      if (!typing) {
        setTurns((prev) => {
          const streamingIdx = findLastIndex(prev, (turn) => turn.streaming);
          if (streamingIdx >= 0) {
            const next = [...prev];
            next[streamingIdx] = { ...next[streamingIdx], streaming: false };
            return next;
          }
          return prev;
        });
        if (!streamingRef.current) {
          setTurns((prev) => {
            const idx = findLastIndex(
              prev,
              (turn) => !turn.streaming && !!turn.messageId && turn.key.startsWith("stream-"),
            );
            if (idx < 0) return prev;
            const turn = prev[idx];
            const next = [...prev];
            next[idx] = { ...turn, key: turn.messageId! };
            return next;
          });
          const tid = activeThreadIdRef.current;
          if (tid) {
            void resolveFeedbackMessageId(tid);
          }
        }
      }
    },
    [resolveFeedbackMessageId],
  );

  const handleAgentTurnTypingChange = useCallback(
    (turnKey: string, typing: boolean, isLastTurn: boolean) => {
      if (typing) {
        if (isLastTurn) {
          isRevealingRef.current = true;
          setLastTurnRevealing(true);
        }
        return;
      }
      if (isLastTurn) {
        isRevealingRef.current = false;
        setLastTurnRevealing(false);
      }
      setTurns((prev) =>
        prev.map((turn) =>
          turn.key === turnKey && turn.streaming ? { ...turn, streaming: false } : turn,
        ),
      );
    },
    [],
  );

  useEffect(() => {
    if (id) activeThreadIdRef.current = id;
  }, [id]);

  useEffect(() => {
    if (thread && !streamingRef.current && !isRevealingRef.current) {
      syncTurnsFromThread();
    }
  }, [thread, syncTurnsFromThread]);

  const updateScrollDownVisible = useCallback(() => {
    const el = getAnswerScrollEl();
    if (!el || turns.length === 0 || activeTab !== "answer") {
      setShowScrollDown(false);
      return;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollDown(distanceFromBottom > 100);
  }, [turns.length, activeTab, getAnswerScrollEl]);

  useEffect(() => {
    updateScrollDownVisible();
  }, [turns, updateScrollDownVisible, activeTab]);

  useEffect(() => {
    const el = getAnswerScrollEl();
    if (!el) return;
    el.addEventListener("scroll", updateScrollDownVisible, { passive: true });
    const ro = new ResizeObserver(() => updateScrollDownVisible());
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", updateScrollDownVisible);
      ro.disconnect();
    };
  }, [updateScrollDownVisible, getAnswerScrollEl]);

  const scrollConversationToBottom = useCallback(() => {
    const el = getAnswerScrollEl();
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [getAnswerScrollEl]);

  /** Прокрутка только при новом вопросе — ответ читаем с начала, без ухода вниз при стриме. */
  useEffect(() => {
    if (activeTab !== "answer") return;
    const active = turns.find((t) => t.streaming);
    if (!active || scrollTurnKeyRef.current === active.key) return;
    scrollTurnKeyRef.current = active.key;
    const el = document.getElementById(`turn-${active.key}`);
    el?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [turns.length, activeTab, turns]);

  const runAgentMessage = useCallback(
    async (text: string, existingThreadId: string | null, fileIds: string[] = []) => {
      if ((!text.trim() && fileIds.length === 0) || streamingRef.current) return;
      const canSend = Boolean(token) || session?.authenticated === true;
      if (!canSend) return;
      const tid = existingThreadId ?? threadId;
      if (!tid) return;

      setAgentError(null);
      setAgentLoading(true);
      setAgentStatusText(t("agentStatusThinking"));
      setSearchPhase("routing");
      const pendingKey = `agent-${Date.now()}`;
      currentThinkingKeyRef.current = pendingKey;
      setAgentThinkingByKey((prev) => ({ ...prev, [pendingKey]: [] }));
      setTurns((prev) => [
        ...prev,
        {
          key: pendingKey,
          query: text,
          attachments: [],
          answer: "",
          sources: [],
          images: [],
          followUps: [],
          needsSearch: false,
          streaming: true,
        },
      ]);

      try {
        const result = await streamAgentMessage(token, tid, text, fileIds, {
          onStatus: (status) => {
            setAgentStatusText(status);
          },
          onThinking: (event) => {
            const key = currentThinkingKeyRef.current;
            if (key) {
              setAgentThinkingByKey((prev) => ({
                ...prev,
                [key]: [...(prev[key] ?? []), event],
              }));
            }
          },
        });
        if (!result) {
          setAgentLoading(false);
          setAgentStatusText(null);
          setSearchPhase("idle");
          setTurns((prev) => prev.filter((turn) => turn.key !== pendingKey));
          return;
        }
        queryClient.invalidateQueries({ queryKey: ["thread", tid] });
        queryClient.invalidateQueries({ queryKey: ["threads"] });
        queryClient.invalidateQueries({ queryKey: ["thread-answer-status", tid] });
        const finalKey = result.assistant_message.id;
        // Переносим thinking-события со временного ключа на финальный messageId
        setAgentThinkingByKey((prev) => {
          const events = prev[pendingKey] ?? [];
          const next = { ...prev };
          delete next[pendingKey];
          if (events.length > 0) next[finalKey] = events;
          return next;
        });
        currentThinkingKeyRef.current = null;
        setTurns((prev) =>
          prev.map((turn) =>
            turn.key === pendingKey
              ? {
                  ...turn,
                  key: finalKey,
                  messageId: finalKey,
                  answer: result.assistant_message.content,
                  sources: result.assistant_message.sources ?? [],
                  streaming: true,
                }
              : turn,
          ),
        );
        setAgentLoading(false);
        setAgentStatusText(null);
        setSearchPhase("idle");
      } catch (err) {
        const msg =
          err instanceof Error && err.message.trim()
            ? err.message
            : "Не удалось отправить сообщение. Попробуйте ещё раз.";
        setAgentLoading(false);
        setAgentStatusText(null);
        setSearchPhase("idle");
        setTurns((prev) => prev.filter((turn) => turn.key !== pendingKey));
        setAgentError(msg);
      }
    },
    [token, session?.authenticated, threadId, queryClient],
  );

  const runSearch = useCallback(
    async (
      text: string,
      existingThreadId: string | null,
      attachmentIds: string[],
      messageAttachments: MessageAttachment[] = [],
      options?: { retryPending?: boolean; resumeTurnKey?: string },
    ) => {
      if (!text.trim() && !attachmentIds.length) return;
      if (streamingRef.current) return;
      if (text.length > SEARCH_QUERY_MAX_LENGTH) {
        const pendingKey = `stream-${Date.now()}`;
        setTurns((prev) => [
          ...prev,
          {
            key: pendingKey,
            query: text,
            attachments: messageAttachments,
            answer: `Запрос слишком длинный (${text.length} символов). Сократите текст до ${SEARCH_QUERY_MAX_LENGTH} символов или отправьте описание частями.`,
            sources: [],
            images: [],
            followUps: [],
            streaming: false,
          },
        ]);
        return;
      }

      setActiveTab("answer");
      const retryPending = Boolean(options?.retryPending);
      const resumeTurnKey = options?.resumeTurnKey;
      const pendingKey = resumeTurnKey ?? `stream-${Date.now()}`;
      const imageGenQuery = !attachmentIds.length && wantsImageGeneration(text);
      imageGenActiveRef.current = imageGenQuery;
      docGenActiveRef.current = false;
      setDocGenStatus(undefined);
      setImageGenStatus(undefined);
      streamingRef.current = true;
      setStreaming(true);
      setNeedsSearch(!imageGenQuery);
      setSearchPhase(imageGenQuery ? "image_generating" : "routing");
      if (retryPending && resumeTurnKey) {
        setTurns((prev) =>
          prev.map((turn) =>
            turn.key === resumeTurnKey
              ? {
                  ...turn,
                  preparing: false,
                  streaming: true,
                  answer: "",
                  sources: [],
                  images: [],
                  followUps: [],
                  errorCode: undefined,
                }
              : turn,
          ),
        );
      } else {
        setTurns((prev) => [
          ...prev,
          {
            key: pendingKey,
            query: text,
            attachments: messageAttachments,
            answer: "",
            sources: [],
            images: [],
            followUps: [],
            needsSearch: !imageGenQuery,
            isImageGen: imageGenQuery,
            streaming: true,
          },
        ]);
      }

      await streamSearch(token, text, existingThreadId, attachmentIds, {
        onThread: (tid) => {
          activeThreadIdRef.current = tid;
          setThreadId(tid);
          if (!id) navigate(`/thread/${tid}`, { replace: true });
        },
        onRoute: (route) => {
          const isDocGen = route.intent === "generate_document";
          const isExportMd = route.intent === "export_chat_document";
          const isImageGen =
            route.intent === "image_generate" || route.reason === "image_generation";
          docGenActiveRef.current = isDocGen;
          imageGenActiveRef.current = isImageGen;
          if (isDocGen || isExportMd) {
            setNeedsSearch(false);
            setSearchPhase("idle");
          }
          setNeedsSearch(route.needs_search);
          if (isImageGen) {
            setSearchPhase("image_generating");
          } else {
            setSearchPhase(route.needs_search ? "searching" : "answering");
          }
          setTurns((prev) =>
            updateLastStreamingTurn(prev, {
              needsSearch: route.needs_search,
              isImageGen,
              isDocumentGen: isDocGen,
            }),
          );
        },
        onMarkdownDocument: (doc) => {
          setTurns((prev) =>
            updateLastStreamingTurn(prev, {
              markdownDocument: doc,
            }),
          );
        },
        onDocGenStart: (status) => {
          setDocGenStatus(status);
        },
        onDocGenStatus: (status) => {
          setDocGenStatus(status);
        },
        onDocumentReady: (doc: GeneratedDocumentInfo) => {
          setTurns((prev) =>
            updateLastStreamingTurn(prev, {
              generatedDocument: {
                id: doc.id,
                filename: doc.filename,
                kind: "document",
                url: doc.url,
                share_url: doc.share_url,
                ttl_hours: doc.ttl_hours,
              },
            }),
          );
        },
        onImageGenStart: (status) => {
          setSearchPhase("image_generating");
          if (status?.trim()) setImageGenStatus(status.trim());
        },
        onImageGenStatus: (status) => {
          setSearchPhase("image_generating");
          if (status?.trim()) setImageGenStatus(status.trim());
        },
        onSources: (list) => {
          setSearchPhase("answering");
          setTurns((prev) => updateLastStreamingTurn(prev, { sources: list ?? [] }));
        },
        onImages: (list) => {
          if (imageGenActiveRef.current) {
            setSearchPhase("idle");
          }
          setTurns((prev) => updateLastStreamingTurn(prev, { images: list ?? [] }));
        },
        onToken: (chunk) => {
          if (!imageGenActiveRef.current) {
            setSearchPhase("answering");
          }
          setTurns((prev) => {
            const idx = findLastIndex(prev, (turn) => turn.streaming);
            if (idx < 0) return prev;
            const current = prev[idx];
            const next = [...prev];
            if (answerResetPendingRef.current) {
              answerResetPendingRef.current = false;
              next[idx] = { ...current, answer: chunk };
            } else {
              next[idx] = { ...current, answer: current.answer + chunk };
            }
            return next;
          });
        },
        onResetAnswer: () => {
          answerResetPendingRef.current = true;
        },
        onFollowUps: (questions) => {
          setTurns((prev) =>
            updateLastActiveTurn(prev, { followUps: (questions ?? []).slice(0, 3) }),
          );
        },
        onDone: (done) => {
          streamingRef.current = false;
          imageGenActiveRef.current = false;
          docGenActiveRef.current = false;
          setDocGenStatus(undefined);
          setImageGenStatus(undefined);
          setStreaming(false);
          setSearchPhase("idle");
          answerResetPendingRef.current = false;
          const messageId = done?.message_id;
          const validMessageId =
            messageId && /^[0-9a-f-]{36}$/i.test(messageId) ? messageId : undefined;
          setTurns((prev) =>
            prev.map((turn) => {
              if (!turn.streaming) return turn;
              const resolvedId = validMessageId ?? turn.messageId;
              return {
                ...turn,
                streaming: false,
                messageId: resolvedId,
                key:
                  resolvedId && turn.key.startsWith("stream-") ? resolvedId : turn.key,
              };
            }),
          );
          queryClient.invalidateQueries({ queryKey: ["session"] });
          queryClient.invalidateQueries({ queryKey: ["threads"] });
          const tid = activeThreadIdRef.current ?? existingThreadId ?? id ?? threadId;
          if (tid) {
            queryClient.invalidateQueries({ queryKey: ["thread", tid] });
            queryClient.invalidateQueries({ queryKey: ["thread-answer-status", tid] });
            if (!validMessageId) {
              void resolveFeedbackMessageId(tid);
            }
          }
        },
        onError: (msg, code) => {
          streamingRef.current = false;
          imageGenActiveRef.current = false;
          docGenActiveRef.current = false;
          setDocGenStatus(undefined);
          setImageGenStatus(undefined);
          setStreaming(false);
          setSearchPhase("idle");
          const threadMissing =
            code === "not_found" || msg.includes("Тред не найден");
          if (threadMissing) {
            activeThreadIdRef.current = null;
            setThreadId(null);
            if (id) navigate("/", { replace: true });
          }
          setTurns((prev) =>
            prev.map((turn) => {
              if (!turn.streaming) return turn;
              if (code === "guest_rate_limit" || (code === "rate_limit" && !token)) {
                return {
                  ...turn,
                  answer: "",
                  errorCode: "guest_rate_limit",
                  streaming: false,
                };
              }
              if (code === "rate_limit" && session?.is_guest) {
                return {
                  ...turn,
                  answer: "",
                  errorCode: "guest_rate_limit",
                  streaming: false,
                };
              }
              if (code === "free_rate_limit") {
                return {
                  ...turn,
                  answer: "",
                  errorCode: "free_rate_limit",
                  streaming: false,
                };
              }
              if (code === "free_image_gen_pro") {
                return {
                  ...turn,
                  answer: "",
                  errorCode: "free_image_gen_pro",
                  streaming: false,
                };
              }
              if (code === "image_gen_rate_limit") {
                return {
                  ...turn,
                  answer: t("imageGenRateLimit"),
                  errorCode: "image_gen_rate_limit",
                  streaming: false,
                };
              }
              if (
                code === "doc_gen_rate_limit" ||
                code === "doc_gen_guest_limit" ||
                code === "doc_gen_format_unavailable"
              ) {
                return {
                  ...turn,
                  answer: msg,
                  errorCode: code,
                  streaming: false,
                };
              }
              if (code === "doc_gen_failed") {
                return {
                  ...turn,
                  answer: msg,
                  streaming: false,
                };
              }
              const keepAnswer = answerHasText(turn.answer);
              return {
                ...turn,
                answer: keepAnswer ? normalizeAnswerText(turn.answer) : normalizeAnswerText(msg),
                streaming: false,
              };
            }),
          );
        },
      }, { retryPending });
    },
    [token, id, navigate, queryClient, threadId, session?.is_guest, resolveFeedbackMessageId],
  );

  const retryPendingTurn = useCallback(
    (turn: ThreadTurn) => {
      const attachmentIds = turn.attachments.map((a) => a.id);
      void runSearch(turn.query, threadId, attachmentIds, turn.attachments, {
        retryPending: true,
        resumeTurnKey: turn.key,
      });
    },
    [runSearch, threadId],
  );

  useEffect(() => {
    if (!threadHasPending) {
      autoResumeRef.current = null;
      autoResumeScheduledRef.current = null;
    }
  }, [threadHasPending]);

  const answerStatusActive = answerStatus?.active ?? false;
  const answerStatusStale = answerStatus?.stale ?? false;
  const pendingTurn = turns[turns.length - 1];
  const pendingTurnKey = pendingTurn?.preparing ? pendingTurn.key : null;

  const pendingPollAgeSec =
    pendingPollStartedAtRef.current !== null
      ? (Date.now() - pendingPollStartedAtRef.current) / 1000
      : 0;
  const pendingActiveAgeSec = answerStatus?.active_age_sec ?? pendingPollAgeSec;
  const forceResumeActive =
    answerStatusActive &&
    !answerStatusStale &&
    pendingActiveAgeSec >= PENDING_ACTIVE_FORCE_RESUME_SEC;

  useEffect(() => {
    if (streaming || !threadHasPending || !activeThreadKey || !pendingTurnKey) return;
    if (!pendingTurn?.preparing || pendingTurn.errorCode || answerHasText(pendingTurn.answer)) return;
    if (!answerStatus) return;
    if (answerStatusActive && !answerStatusStale && !forceResumeActive) return;

    const turnKey = pendingTurnKey;
    const priorAttempts =
      autoResumeRef.current?.turnKey === turnKey ? autoResumeRef.current.attempts : 0;

    if (priorAttempts >= AUTO_RESUME_MAX_ATTEMPTS) {
      if (pendingTurn.preparing && !pendingTurn.errorCode) {
        setTurns((prev) =>
          prev.map((turn) =>
            turn.key === turnKey
              ? { ...turn, preparing: false, errorCode: "search_interrupted" }
              : turn,
          ),
        );
      }
      return;
    }

    const scheduleKey = `${turnKey}:${priorAttempts}:${
      answerStatusStale || forceResumeActive ? "stale" : "wait"
    }`;
    if (autoResumeScheduledRef.current === scheduleKey) return;
    autoResumeScheduledRef.current = scheduleKey;

    const turnSnapshot = pendingTurn;
    const delay = answerStatusStale || forceResumeActive ? 0 : AUTO_RESUME_GRACE_MS;
    const timer = window.setTimeout(() => {
      void (async () => {
        if (streamingRef.current) return;
        try {
          const fresh = await fetchThread(token, activeThreadKey);
          queryClient.setQueryData(["thread", activeThreadKey], fresh);
          if (!threadHasPendingAnswer(fresh.messages)) return;
        } catch {
          return;
        }

        const nextAttempt =
          (autoResumeRef.current?.turnKey === turnKey
            ? autoResumeRef.current.attempts
            : 0) + 1;
        autoResumeRef.current = { turnKey, attempts: nextAttempt };
        autoResumeScheduledRef.current = null;

        if (nextAttempt > AUTO_RESUME_MAX_ATTEMPTS) {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.key === turnKey
                ? { ...turn, preparing: false, errorCode: "search_interrupted" }
                : turn,
            ),
          );
          return;
        }

        retryPendingTurn(turnSnapshot);
      })();
    }, delay);

    return () => window.clearTimeout(timer);
  }, [
    streaming,
    threadHasPending,
    pendingTurn,
    pendingTurnKey,
    answerStatus,
    answerStatusActive,
    answerStatusStale,
    forceResumeActive,
    activeThreadKey,
    token,
    queryClient,
    retryPendingTurn,
  ]);

  useEffect(() => {
    if (isAgentThread) return;
    if (!(initialQuery || initialFiles.length) || id || started.current) return;
    started.current = true;
    const pending = (location.state as ThreadLocationState | null)?.pendingAttachments;
    if (pending?.length) {
      runSearch(initialQuery || t("analyzeFile"), null, initialFiles, pending);
      return;
    }
    if (!token || !initialFiles.length) {
      runSearch(initialQuery || t("analyzeFile"), null, initialFiles, []);
      return;
    }
    void (async () => {
      const metas = await Promise.all(
        initialFiles.map(async (fileId) => {
          try {
            const meta = await fetchFileMeta(token, fileId);
            return {
              id: meta.id,
              filename: meta.filename,
              kind: (meta.media_kind === "image" ? "image" : "document") as "image" | "document",
              url: meta.preview_url ?? undefined,
            } satisfies MessageAttachment;
          } catch {
            return null;
          }
        }),
      );
      runSearch(
        initialQuery || t("analyzeFile"),
        null,
        initialFiles,
        metas.filter((m): m is MessageAttachment => m !== null),
      );
    })();
  }, [initialQuery, initialFiles, id, runSearch, token, location.state, isAgentThread]);

  const onComposerSubmit = (payload: {
    query: string;
    attachmentIds: string[];
    attachments: ComposerAttachment[];
  }) => {
    if (isAgentThread) {
      // В агентском треде ВСЕ сообщения идут в агент — без keyword-роутинга.
      // Агент сам решает что делать: выполнить сразу или настроить автоматизацию.
      void runAgentMessage(payload.query, threadId, payload.attachmentIds);
      return;
    }
    runSearch(
      payload.query,
      threadId,
      payload.attachmentIds,
      mapComposerAttachments(payload.attachments),
    );
  };

  const startNewAgentThread = useCallback(async () => {
    navigate("/agents");
  }, [navigate]);

  const lastCompletedIndex = findLastIndex(
    turns,
    (turn) => !turn.streaming && answerHasText(turn.answer),
  );

  const showImagesTab = !isAgentThread && threadHasSearchTurns(turns);
  const totalImages = countThreadImages(turns);
  const imageGroups = useMemo(() => buildThreadImageGroups(turns), [turns]);
  const lastTurn = turns[turns.length - 1];
  const imagesLoading = Boolean(
    streaming &&
      lastTurn?.streaming &&
      (lastTurn.images?.length ?? 0) === 0 &&
      (lastTurn.needsSearch || searchPhase === "image_generating"),
  );

  /** Мобилка: вкладка «Изображения» — новые фото сверху, сбрасываем scroll ответа. */
  useEffect(() => {
    if (isDesktop || activeTab !== "images") return;
    const el = imagesPanelRef.current;
    if (!el) return;
    const scrollToTop = () => {
      el.scrollTop = 0;
    };
    scrollToTop();
    requestAnimationFrame(scrollToTop);
  }, [activeTab, isDesktop, imageGroups.length, imagesLoading]);

  return (
    <div className={`page page-thread${isDesktop ? "" : " page-thread--mobile"}`}>
      {!isDesktop && (
        <ThreadMobileHeader
          onBack={() => navigate(fromHistory ? "/history" : "/")}
          activeTab={activeTab}
          onTabChange={handleTabChange}
          showImagesTab={showImagesTab}
          totalImages={totalImages}
        />
      )}

      {isDesktop && turns.length > 0 && (
        <ThreadTabsBar
          activeTab={activeTab}
          onTabChange={handleTabChange}
          showImagesTab={showImagesTab}
          totalImages={totalImages}
        />
      )}

      <div className={`thread-mobile-body${isDesktop ? " thread-mobile-body--desktop" : ""}`}>
      <div
        className={`thread-conversation${isDesktop ? "" : " thread-conversation--mobile-tabs"}`}
        ref={conversationRef}
      >
        <div
          className="thread-panel thread-panel--answer"
          ref={answerPanelRef}
          hidden={activeTab !== "answer"}
        >
          {turns.map((turn, index) => {
            const isActive = turn.streaming;
            const sources = turn.sources ?? [];
            const answerText = displayAnswerText(normalizeAnswerText(turn.answer), sources);
            const isImageGenTurn = useChatGeneratedImageLayout(turn);
            const isDocumentGenTurn = Boolean(turn.isDocumentGen || turn.generatedDocument);
            const isLastTurn = index === turns.length - 1;
            const turnAnswerStatus: AnswerStatus | undefined =
              isLastTurn && (turn.preparing || (isAgentThread && agentLoading))
                ? answerStatus
                : undefined;
            const showPreparing = Boolean(
              turn.preparing && !streaming && !turn.errorCode && !answerHasText(turn.answer),
            );
            const preparingPhase = turnAnswerStatus?.active
              ? answerStatusPhaseToSearchPhase(
                  turnAnswerStatus.phase,
                  turnAnswerStatus.needs_search,
                )
              : "preparing";
            const preparingNeedsSearch =
              turnAnswerStatus?.needs_search ?? turn.needsSearch ?? needsSearch;
            const showInterrupted = turn.errorCode === "search_interrupted";
            const showAgentStatus =
              isAgentThread &&
              isLastTurn &&
              agentLoading &&
              !answerHasText(turn.answer) &&
              !turn.errorCode;
            const showStatus =
              showAgentStatus ||
              showPreparing ||
              (isActive &&
                (isAgentThread || streaming) &&
                !turn.errorCode &&
                (isDocumentGenTurn
                  ? !answerHasText(turn.answer) && !turn.generatedDocument
                  : isImageGenTurn
                    ? (turn.images?.length ?? 0) === 0
                    : !answerHasText(turn.answer)));
            const showGuestLimit = turn.errorCode === "guest_rate_limit" || turn.errorCode === "rate_limit";
            const showFreeLimit = turn.errorCode === "free_rate_limit";
            const showImageGenPro = turn.errorCode === "free_image_gen_pro";
            const showEntityImages =
              (turn.images?.length ?? 0) > 0 &&
              (isImageGenTurn ||
                (isLastTurn && !streaming && !lastTurnRevealing) ||
                (!isLastTurn && !isActive));
            const unifiedDoc = resolveUnifiedDocument(turn.answer, turn.markdownDocument);
            const showAnswer =
              showInterrupted ||
              showGuestLimit ||
              showFreeLimit ||
              showImageGenPro ||
              answerHasText(turn.answer) ||
              Boolean(unifiedDoc) ||
              Boolean(turn.markdownDocument) ||
              Boolean(turn.generatedDocument) ||
              (isImageGenTurn && (turn.images?.length ?? 0) > 0) ||
              showEntityImages ||
              isActive;
            const showFollowUps =
              index === lastCompletedIndex &&
              turn.followUps.length > 0 &&
              !streaming &&
              !isActive;

            if (turn.agentActivityLog && threadId) {
              return (
                <article key={turn.key} id={`turn-${turn.key}`} className="thread-turn thread-turn--agent-log">
                  <AgentActivityLogPanel
                    threadId={threadId}
                    token={token}
                    summaryLabel={turn.agentActivityLogSummary}
                  />
                </article>
              );
            }

            return (
              <article key={turn.key} id={`turn-${turn.key}`} className="thread-turn">
                {(turn.query.trim() || turn.attachments.length > 0) && (
                  <ThreadQuery query={turn.query} attachments={turn.attachments} />
                )}

                {showStatus &&
                  (showPreparing && preparingPhase === "image_generating" ? (
                    <ImageGenStatusLine
                      active
                      status={imageGenStatus ?? turnAnswerStatus?.custom_status ?? undefined}
                    />
                  ) : showPreparing ? (
                    <SearchStatusLine
                      phase={preparingPhase}
                      needsSearch={preparingNeedsSearch}
                      customStatus={turnAnswerStatus?.custom_status}
                    />
                  ) : isDocumentGenTurn ? (
                    <DocGenStatusLine active={Boolean(isActive && streaming)} status={docGenStatus} />
                  ) : isImageGenTurn ? (
                    <ImageGenStatusLine
                      active={Boolean(isActive && streaming)}
                      status={imageGenStatus ?? turnAnswerStatus?.custom_status ?? undefined}
                    />
                  ) : showAgentStatus ? (
                    <>
                      <SearchStatusLine
                        phase="routing"
                        needsSearch={false}
                        customStatus={
                          agentStatusText ??
                          turnAnswerStatus?.custom_status ??
                          t("agentStatusThinking")
                        }
                      />
                      {(agentThinkingByKey[turn.key]?.length ?? 0) > 0 && (
                        <AgentThinkingPanel
                          events={agentThinkingByKey[turn.key] ?? []}
                          isActive={agentLoading}
                        />
                      )}
                    </>
                  ) : (
                    <SearchStatusLine phase={searchPhase} needsSearch={needsSearch} />
                  ))}

                {isAgentThread && (agentThinkingByKey[turn.key]?.length ?? 0) > 0 && !showAgentStatus && (
                  <AgentThinkingPanel
                    events={agentThinkingByKey[turn.key] ?? []}
                    isActive={isLastTurn && agentLoading}
                  />
                )}

                {showAnswer && (
                  <section className="answer-section">
                    <AnswerErrorBoundary>
                      {showInterrupted ? (
                        <div className="answer">
                          <div className="answer-text">
                            <p>{t("answerInterrupted")}</p>
                            <p>
                              <button
                                type="button"
                                className="btn-link answer-retry-link"
                                disabled={streaming}
                                onClick={() => retryPendingTurn(turn)}
                              >
                                {t("retrySearch")}
                              </button>
                            </p>
                          </div>
                        </div>
                      ) : showGuestLimit ? (
                        <GuestLimitNotice />
                      ) : showFreeLimit ? (
                        <FreeLimitNotice />
                      ) : showImageGenPro ? (
                        <ImageGenProNotice />
                      ) : unifiedDoc ? (
                        <div className="answer">
                          {unifiedDoc.intro ? (
                            <div className="answer-text">
                              {renderAnswerTextSegment(unifiedDoc.intro, sources, `u-intro-${index}`)}
                            </div>
                          ) : null}
                          <DocumentAnswerBlock
                            markdownParts={unifiedDoc.markdownParts}
                            charts={unifiedDoc.charts}
                          />
                        </div>
                      ) : (
                        <AnswerBody
                          text={answerText}
                          sources={sources}
                          isStreaming={
                            isActive &&
                            (isAgentThread ? answerHasText(turn.answer) : streaming) &&
                            !isImageGenTurn &&
                            !isDocumentGenTurn
                          }
                          revealByAnimationOnly={isAgentThread}
                          onTypingChange={
                            isAgentThread &&
                            turn.streaming &&
                            (turn.agentWelcome || answerHasText(turn.answer))
                              ? (typing) =>
                                  handleAgentTurnTypingChange(
                                    turn.key,
                                    typing,
                                    index === turns.length - 1,
                                  )
                              : index === turns.length - 1
                                ? handleAnswerTypingChange
                                : undefined
                          }
                        />
                      )}
                    </AnswerErrorBoundary>
                    {turn.markdownDocument && !unifiedDoc ? (
                      <CollapsibleMarkdownDocument
                        title={turn.markdownDocument.title}
                        content={turn.markdownDocument.content}
                        collapsible={turn.markdownDocument.collapsible}
                      />
                    ) : null}
                    {turn.generatedDocument && (
                      <GeneratedDocumentCard document={turn.generatedDocument} />
                    )}
                    {showEntityImages && (
                      <div className="answer-generated-media">
                        {isImageGenTurn ? (
                          <ChatGeneratedImages images={turn.images} />
                        ) : (
                          <TurnImageGallery images={turn.images} />
                        )}
                      </div>
                    )}
                    {(answerHasText(turn.answer) || turn.generatedDocument || turn.markdownDocument) && (
                      <AnswerFooter
                        answer={answerText}
                        title={turn.query}
                        sources={sources}
                        messageId={resolveAssistantMessageId(turn)}
                        token={token}
                        userFeedback={turn.userFeedback}
                        generatedDocument={turn.generatedDocument ?? null}
                      />
                    )}
                  </section>
                )}

                {showFollowUps && (
                  <section className="followups-section">
                    <h3 className="followups-heading">{t("followUps")}</h3>
                    <ul className="followups-list">
                      {turn.followUps.slice(0, 3).map((q) => (
                        <li key={q}>
                          <button
                            type="button"
                            className="followup-item"
                            disabled={streaming}
                            onClick={() => runSearch(q, threadId, [])}
                          >
                            {q}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </article>
            );
          })}
        </div>

        <div
          className="thread-panel thread-panel--images"
          ref={imagesPanelRef}
          hidden={activeTab !== "images"}
        >
          <ThreadImagesTab groups={imageGroups} loading={imagesLoading} />
        </div>
      </div>

      {showScrollDown && activeTab === "answer" && (
        <button
          type="button"
          className="thread-scroll-down"
          onClick={scrollConversationToBottom}
          aria-label={t("scrollToBottom")}
          title={t("scrollToBottom")}
        >
          <ScrollDownIcon />
        </button>
      )}

      <SearchComposer
        value={composerQuery}
        onChange={setComposerQuery}
        onSubmit={(p) => {
          setComposerQuery("");
          onComposerSubmit(p);
        }}
        disabled={isAgentThread ? agentLoading : streaming}
        placeholder={isAgentThread ? t("agentComposerPlaceholder") : t("askFollowUp")}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        requireTextWithAttachments={isAgentThread || (!isAgentThread && turns.length === 0)}
        layoutMode={isDesktop ? "default" : "threadMobile"}
        onNewChat={isDesktop ? undefined : () => navigate("/")}
        onAgentClick={startNewAgentThread}
        agentStarting={agentStarting}
        agentError={agentError}
        agentMode={isAgentThread}
      />
      </div>
    </div>
  );
}

function ScrollDownIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5v14M6 13l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
