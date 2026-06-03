import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  fetchFileMeta,
  fetchThread,
  fetchSession,
  streamSearch,
  type GeneratedDocumentInfo,
  type MessageAttachment,
} from "../api/client";
import { AnswerBody } from "../components/AnswerBody";
import { AnswerErrorBoundary } from "../components/AnswerErrorBoundary";
import { AnswerFooter } from "../components/AnswerFooter";
import { FreeLimitNotice } from "../components/FreeLimitNotice";
import { GuestLimitNotice } from "../components/GuestLimitNotice";
import { ChatGeneratedImages } from "../components/ChatGeneratedImages";
import { ImageGenProNotice } from "../components/ImageGenProNotice";
import { ImageGenStatusLine } from "../components/ImageGenStatusLine";
import { DocGenStatusLine } from "../components/DocGenStatusLine";
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
import { mergeThreadTurns, messagesToTurns, resolveAssistantMessageId, type ThreadTurn } from "../lib/threadTurns";
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
    answer: appendAnswer !== undefined ? current.answer + appendAnswer : (patch.answer ?? current.answer),
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
    (turn) => turn.streaming || Boolean(turn.messageId) || Boolean(turn.answer.trim()),
  );
  if (idx < 0) return turns;
  const next = [...turns];
  next[idx] = { ...next[idx], ...patch };
  return next;
}

type ThreadLocationState = {
  fromHistory?: boolean;
  pendingAttachments?: MessageAttachment[];
};

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
  const guestSearchLimit = session?.searches_limit ?? 5;

  const [threadId, setThreadId] = useState<string | null>(id ?? null);
  const [turns, setTurns] = useState<ThreadTurn[]>([]);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [needsSearch, setNeedsSearch] = useState(true);
  const [searchPhase, setSearchPhase] = useState<SearchPhase>("idle");
  const [composerQuery, setComposerQuery] = useState("");
  const [activeTab, setActiveTab] = useState<ThreadTab>("answer");
  const started = useRef(false);
  const streamingRef = useRef(false);
  const isRevealingRef = useRef(false);
  const activeThreadIdRef = useRef<string | null>(id ?? null);
  const scrollTurnKeyRef = useRef<string | null>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const answerPanelRef = useRef<HTMLDivElement>(null);
  const imagesPanelRef = useRef<HTMLDivElement>(null);
  const answerResetPendingRef = useRef(false);
  const imageGenActiveRef = useRef(false);
  const docGenActiveRef = useRef(false);
  const [docGenStatus, setDocGenStatus] = useState<string | undefined>();
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

  const { data: thread } = useQuery({
    queryKey: ["thread", id ?? threadId],
    queryFn: () => fetchThread(token, (id ?? threadId)!),
    enabled: !!(id ?? threadId),
  });

  const syncTurnsFromThread = useCallback(() => {
    if (!thread) return;
    setTurns((prev) => mergeThreadTurns(prev, messagesToTurns(thread.messages)));
  }, [thread]);

  const handleAnswerTypingChange = useCallback(
    (typing: boolean) => {
      isRevealingRef.current = typing;
      if (!typing && !streamingRef.current) {
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
      }
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

  const runSearch = useCallback(
    async (
      text: string,
      existingThreadId: string | null,
      attachmentIds: string[],
      messageAttachments: MessageAttachment[] = [],
    ) => {
      if (!text.trim() && !attachmentIds.length) return;
      if (streamingRef.current) return;

      setActiveTab("answer");
      const pendingKey = `stream-${Date.now()}`;
      const imageGenQuery = !attachmentIds.length && wantsImageGeneration(text);
      imageGenActiveRef.current = imageGenQuery;
      docGenActiveRef.current = false;
      setDocGenStatus(undefined);
      streamingRef.current = true;
      setStreaming(true);
      setNeedsSearch(!imageGenQuery);
      setSearchPhase(imageGenQuery ? "image_generating" : "routing");
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

      await streamSearch(token, text, existingThreadId, attachmentIds, {
        onThread: (tid) => {
          activeThreadIdRef.current = tid;
          setThreadId(tid);
          if (!id) navigate(`/thread/${tid}`, { replace: true });
        },
        onRoute: (route) => {
          const isDocGen = route.intent === "generate_document";
          const isImageGen =
            route.intent === "image_generate" || route.reason === "image_generation";
          docGenActiveRef.current = isDocGen;
          imageGenActiveRef.current = isImageGen;
          if (isDocGen) {
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
        onImageGenStart: () => {
          setSearchPhase("image_generating");
        },
        onImageGenStatus: () => {
          setSearchPhase("image_generating");
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
          setStreaming(false);
          setSearchPhase("idle");
          answerResetPendingRef.current = false;
          const messageId = done?.message_id;
          setTurns((prev) =>
            prev.map((turn) => {
              if (!turn.streaming) return turn;
              return {
                ...turn,
                streaming: false,
                messageId:
                  messageId && /^[0-9a-f-]{36}$/i.test(messageId) ? messageId : turn.messageId,
              };
            }),
          );
          queryClient.invalidateQueries({ queryKey: ["session"] });
          queryClient.invalidateQueries({ queryKey: ["threads"] });
          const tid = activeThreadIdRef.current ?? existingThreadId ?? id ?? threadId;
          if (tid) queryClient.invalidateQueries({ queryKey: ["thread", tid] });
        },
        onError: (msg, code) => {
          streamingRef.current = false;
          imageGenActiveRef.current = false;
          docGenActiveRef.current = false;
          setDocGenStatus(undefined);
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
              const keepAnswer = turn.answer.trim().length > 0;
              return {
                ...turn,
                answer: keepAnswer ? turn.answer : msg,
                streaming: false,
              };
            }),
          );
        },
      });
    },
    [token, id, navigate, queryClient, threadId, session?.is_guest],
  );

  useEffect(() => {
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
  }, [initialQuery, initialFiles, id, runSearch, token, location.state]);

  const onComposerSubmit = (payload: {
    query: string;
    attachmentIds: string[];
    attachments: ComposerAttachment[];
  }) => {
    runSearch(
      payload.query,
      threadId,
      payload.attachmentIds,
      mapComposerAttachments(payload.attachments),
    );
  };

  const lastCompletedIndex = findLastIndex(
    turns,
    (turn) => !turn.streaming && turn.answer.trim(),
  );

  const showImagesTab = threadHasSearchTurns(turns);
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
    <div className="page page-thread">
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
            const isImageGenTurn = useChatGeneratedImageLayout(turn);
            const isDocumentGenTurn = Boolean(turn.isDocumentGen || turn.generatedDocument);
            const showStatus =
              isActive &&
              streaming &&
              !turn.errorCode &&
              (isDocumentGenTurn
                ? !turn.answer.trim() && !turn.generatedDocument
                : isImageGenTurn
                  ? (turn.images?.length ?? 0) === 0
                  : !turn.answer.trim());
            const showGuestLimit = turn.errorCode === "guest_rate_limit" || turn.errorCode === "rate_limit";
            const showFreeLimit = turn.errorCode === "free_rate_limit";
            const showImageGenPro = turn.errorCode === "free_image_gen_pro";
            const showAnswer =
              showGuestLimit ||
              showFreeLimit ||
              showImageGenPro ||
              Boolean(turn.answer.trim()) ||
              Boolean(turn.generatedDocument) ||
              (turn.images?.length ?? 0) > 0 ||
              isActive;
            const showFollowUps =
              index === lastCompletedIndex &&
              turn.followUps.length > 0 &&
              !streaming &&
              !isActive;

            return (
              <article key={turn.key} id={`turn-${turn.key}`} className="thread-turn">
                <ThreadQuery query={turn.query} attachments={turn.attachments} />

                {showStatus &&
                  (isDocumentGenTurn ? (
                    <DocGenStatusLine active={streaming} status={docGenStatus} />
                  ) : isImageGenTurn ? (
                    <ImageGenStatusLine active={streaming} />
                  ) : (
                    <SearchStatusLine phase={searchPhase} needsSearch={needsSearch} />
                  ))}

                {showAnswer && (
                  <section className="answer-section">
                    <AnswerErrorBoundary>
                      {showGuestLimit ? (
                        <GuestLimitNotice limit={guestSearchLimit} />
                      ) : showFreeLimit ? (
                        <FreeLimitNotice />
                      ) : showImageGenPro ? (
                        <ImageGenProNotice />
                      ) : (
                        <AnswerBody
                          text={turn.answer}
                          sources={sources}
                          isStreaming={
                            isActive && streaming && !isImageGenTurn && !isDocumentGenTurn
                          }
                          onTypingChange={
                            index === turns.length - 1 ? handleAnswerTypingChange : undefined
                          }
                        />
                      )}
                    </AnswerErrorBoundary>
                    {turn.generatedDocument && (
                      <GeneratedDocumentCard document={turn.generatedDocument} />
                    )}
                    {(turn.images?.length ?? 0) > 0 && (
                      <div className="answer-generated-media">
                        {isImageGenTurn ? (
                          <ChatGeneratedImages images={turn.images} />
                        ) : (
                          <TurnImageGallery images={turn.images} />
                        )}
                      </div>
                    )}
                    {(turn.answer.trim() || turn.generatedDocument) && (
                      <AnswerFooter
                        answer={turn.answer}
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
        disabled={streaming}
        placeholder={t("askFollowUp")}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        requireTextWithAttachments={turns.length === 0}
        layoutMode={isDesktop ? "default" : "threadMobile"}
        onNewChat={isDesktop ? undefined : () => navigate("/")}
      />
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
