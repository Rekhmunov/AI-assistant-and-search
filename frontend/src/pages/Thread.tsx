import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchThread, streamSearch } from "../api/client";
import { AnswerBody } from "../components/AnswerBody";
import { AnswerErrorBoundary } from "../components/AnswerErrorBoundary";
import { AnswerFooter } from "../components/AnswerFooter";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SearchStatusLine, type SearchPhase } from "../components/SearchStatusLine";
import { t } from "../i18n";
import { findLastIndex } from "../lib/arrayUtils";
import { messagesToTurns, type ThreadTurn } from "../lib/threadTurns";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useAuthStore } from "../store/authStore";

function updateLastStreamingTurn(
  turns: ThreadTurn[],
  patch: Partial<Pick<ThreadTurn, "answer" | "sources" | "followUps">>,
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

type ThreadLocationState = { fromHistory?: boolean };

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

  const [threadId, setThreadId] = useState<string | null>(id ?? null);
  const [turns, setTurns] = useState<ThreadTurn[]>([]);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [needsSearch, setNeedsSearch] = useState(true);
  const [searchPhase, setSearchPhase] = useState<SearchPhase>("idle");
  const [composerQuery, setComposerQuery] = useState("");
  const started = useRef(false);
  const streamingRef = useRef(false);
  const isRevealingRef = useRef(false);
  const activeThreadIdRef = useRef<string | null>(id ?? null);
  const scrollTurnKeyRef = useRef<string | null>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const answerResetPendingRef = useRef(false);
  const [showScrollDown, setShowScrollDown] = useState(false);
  const isDesktop = useDesktopLayout();

  const { data: thread } = useQuery({
    queryKey: ["thread", id ?? threadId],
    queryFn: () => fetchThread(token, (id ?? threadId)!),
    enabled: !!(id ?? threadId),
  });

  const syncTurnsFromThread = useCallback(() => {
    if (!thread) return;
    setTurns(messagesToTurns(thread.messages));
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
        syncTurnsFromThread();
      }
    },
    [syncTurnsFromThread],
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
    const el = conversationRef.current;
    if (!el || turns.length === 0) {
      setShowScrollDown(false);
      return;
    }
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollDown(distanceFromBottom > 100);
  }, [turns.length]);

  useEffect(() => {
    updateScrollDownVisible();
  }, [turns, updateScrollDownVisible]);

  useEffect(() => {
    const el = conversationRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateScrollDownVisible, { passive: true });
    const ro = new ResizeObserver(() => updateScrollDownVisible());
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", updateScrollDownVisible);
      ro.disconnect();
    };
  }, [updateScrollDownVisible]);

  const scrollConversationToBottom = useCallback(() => {
    const el = conversationRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  /** Прокрутка только при новом вопросе — ответ читаем с начала, без ухода вниз при стриме. */
  useEffect(() => {
    const active = turns.find((t) => t.streaming);
    if (!active || scrollTurnKeyRef.current === active.key) return;
    scrollTurnKeyRef.current = active.key;
    const el = document.getElementById(`turn-${active.key}`);
    el?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [turns.length]);

  const runSearch = useCallback(
    async (text: string, existingThreadId: string | null, attachmentIds: string[]) => {
      if (!text.trim() && !attachmentIds.length) return;
      if (streamingRef.current) return;

      const pendingKey = `stream-${Date.now()}`;
      streamingRef.current = true;
      setStreaming(true);
      setNeedsSearch(true);
      setSearchPhase("routing");
      setTurns((prev) => [
        ...prev,
        {
          key: pendingKey,
          query: text,
          answer: "",
          sources: [],
          followUps: [],
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
          setNeedsSearch(route.needs_search);
          setSearchPhase(route.needs_search ? "searching" : "answering");
        },
        onSources: (list) => {
          setSearchPhase("answering");
          setTurns((prev) => updateLastStreamingTurn(prev, { sources: list }));
        },
        onToken: (chunk) => {
          setSearchPhase("answering");
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
          setTurns((prev) => updateLastStreamingTurn(prev, { followUps: questions }));
        },
        onDone: (done) => {
          streamingRef.current = false;
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
            prev.map((turn) =>
              turn.streaming ? { ...turn, answer: msg, streaming: false } : turn,
            ),
          );
        },
      });
    },
    [token, id, navigate, queryClient, threadId],
  );

  useEffect(() => {
    if ((initialQuery || initialFiles.length) && !id && !started.current) {
      started.current = true;
      runSearch(initialQuery || t("analyzeFile"), null, initialFiles);
    }
  }, [initialQuery, initialFiles, id, runSearch]);

  const onComposerSubmit = (payload: { query: string; attachmentIds: string[] }) => {
    runSearch(payload.query, threadId, payload.attachmentIds);
  };

  const lastCompletedIndex = findLastIndex(
    turns,
    (turn) => !turn.streaming && turn.answer.trim(),
  );

  return (
    <div className="page page-thread">
      {!isDesktop && (
        <div className="thread-top">
          <button
            type="button"
            className="icon-btn icon-btn-back"
            onClick={() => navigate(fromHistory ? "/history" : "/")}
            aria-label={t("back")}
            title={t("back")}
          >
            <BackIcon />
          </button>
        </div>
      )}

      <div className="thread-conversation" ref={conversationRef}>
        {turns.map((turn, index) => {
          const isActive = turn.streaming;
          const showStatus = isActive && streaming && !turn.answer.trim();
          const showAnswer = Boolean(turn.answer.trim()) || isActive;
          const showFollowUps =
            index === lastCompletedIndex &&
            turn.followUps.length > 0 &&
            !streaming &&
            !isActive;

          return (
            <article key={turn.key} id={`turn-${turn.key}`} className="thread-turn">
              <div className="thread-query">
                <p className="thread-query-text">{turn.query}</p>
              </div>

              {showStatus && (
                <SearchStatusLine phase={searchPhase} needsSearch={needsSearch} />
              )}

              {showAnswer && (
                <section className="answer-section">
                  <AnswerErrorBoundary>
                    <AnswerBody
                      text={turn.answer}
                      sources={turn.sources}
                      isStreaming={isActive && streaming}
                      onTypingChange={
                        index === turns.length - 1 ? handleAnswerTypingChange : undefined
                      }
                    />
                  </AnswerErrorBoundary>
                  {!isActive && turn.answer.trim() && (
                    <AnswerFooter
                      answer={turn.answer}
                      title={turn.query}
                      sources={turn.sources}
                      messageId={turn.messageId ?? turn.key}
                      token={token}
                      userFeedback={turn.userFeedback}
                    />
                  )}
                </section>
              )}

              {showFollowUps && (
                <section className="followups-section">
                  <ul className="followups-list">
                    {turn.followUps.map((q) => (
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

      {showScrollDown && (
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
      />
    </div>
  );
}

function BackIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 6l-6 6 6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
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
