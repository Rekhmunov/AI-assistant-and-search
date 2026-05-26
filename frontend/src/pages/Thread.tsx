import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchThread, streamSearch } from "../api/client";
import { AnswerBody } from "../components/AnswerBody";
import { AnswerFooter } from "../components/AnswerFooter";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SearchStatusLine, type SearchPhase } from "../components/SearchStatusLine";
import { t } from "../i18n";
import { messagesToTurns, type ThreadTurn } from "../lib/threadTurns";
import { useAuthStore } from "../store/authStore";

function updateLastStreamingTurn(
  turns: ThreadTurn[],
  patch: Partial<Pick<ThreadTurn, "answer" | "sources" | "followUps">>,
  appendAnswer?: string,
): ThreadTurn[] {
  const idx = turns.findLastIndex((turn) => turn.streaming);
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

export function Thread() {
  const { id } = useParams();
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
  const activeThreadIdRef = useRef<string | null>(id ?? null);
  const scrollTurnKeyRef = useRef<string | null>(null);

  const { data: thread } = useQuery({
    queryKey: ["thread", id ?? threadId],
    queryFn: () => fetchThread(token, (id ?? threadId)!),
    enabled: !!(id ?? threadId),
  });

  useEffect(() => {
    if (id) activeThreadIdRef.current = id;
  }, [id]);

  useEffect(() => {
    if (thread && !streamingRef.current) {
      setTurns(messagesToTurns(thread.messages));
    }
  }, [thread]);

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
          setTurns((prev) => updateLastStreamingTurn(prev, {}, chunk));
        },
        onResetAnswer: () => {
          setTurns((prev) => updateLastStreamingTurn(prev, { answer: "" }));
        },
        onFollowUps: (questions) => {
          setTurns((prev) => updateLastStreamingTurn(prev, { followUps: questions }));
        },
        onDone: () => {
          streamingRef.current = false;
          setStreaming(false);
          setSearchPhase("idle");
          setTurns((prev) =>
            prev.map((turn) => (turn.streaming ? { ...turn, streaming: false } : turn)),
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

  const lastCompletedIndex = turns.findLastIndex((turn) => !turn.streaming && turn.answer.trim());

  return (
    <div className="page page-thread">
      <div className="thread-top">
        <button
          type="button"
          className="icon-btn icon-btn-back"
          onClick={() => navigate("/")}
          aria-label={t("back")}
          title={t("back")}
        >
          <BackIcon />
        </button>
      </div>

      <div className="thread-conversation">
        {turns.length === 0 && !streaming && (
          <p className="thread-conversation-empty">{t("loading")}</p>
        )}

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
                  <AnswerBody text={turn.answer} sources={turn.sources} />
                  {!isActive && turn.answer.trim() && (
                    <AnswerFooter
                      answer={turn.answer}
                      title={turn.query}
                      sources={turn.sources}
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
