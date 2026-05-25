import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchThread, saveThread, streamSearch, type Source } from "../api/client";
import { AnswerToolbar } from "../components/AnswerToolbar";
import { GlosixHeader } from "../components/GlosixHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SearchStatusLine, type SearchPhase } from "../components/SearchStatusLine";
import { SourcesCollapsible } from "../components/SourcesCollapsible";
import { StreamingText } from "../components/StreamingText";
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
  const [saved, setSaved] = useState(false);
  const [needsSearch, setNeedsSearch] = useState(true);
  const [searchPhase, setSearchPhase] = useState<SearchPhase>("idle");
  const [composerQuery, setComposerQuery] = useState("");
  const started = useRef(false);
  const streamingRef = useRef(false);
  const activeThreadIdRef = useRef<string | null>(id ?? null);
  const scrollBottomRef = useRef<HTMLDivElement>(null);

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
      setSaved(thread.is_saved);
      setTurns(messagesToTurns(thread.messages));
    }
  }, [thread]);

  useEffect(() => {
    scrollBottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth" });
  }, [turns, streaming, searchPhase]);

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
        onError: (msg) => {
          streamingRef.current = false;
          setStreaming(false);
          setSearchPhase("idle");
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

  const handleSave = async () => {
    if (!threadId || !token) return;
    await saveThread(token, threadId);
    setSaved(true);
  };

  const onComposerSubmit = (payload: { query: string; attachmentIds: string[] }) => {
    runSearch(payload.query, threadId, payload.attachmentIds);
  };

  const lastCompletedIndex = turns.findLastIndex((turn) => !turn.streaming && turn.answer.trim());

  return (
    <div className="page page-thread">
      <div className="thread-top">
        <GlosixHeader showLimits={false} />
        <div className="thread-actions">
          <button type="button" className="icon-btn" onClick={() => navigate("/")}>
            ← {t("back")}
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={handleSave}
            disabled={!token || !threadId || saved}
            title={!token ? t("loginToSave") : undefined}
          >
            {saved ? t("saved") : t("save")}
          </button>
        </div>
      </div>

      <div className="thread-conversation">
        {turns.length === 0 && !streaming && (
          <p className="thread-conversation-empty">{t("loading")}</p>
        )}

        {turns.map((turn, index) => {
          const isActive = turn.streaming;
          const showStatus = isActive && streaming && !turn.answer.trim();
          const showAnswer = Boolean(turn.answer.trim()) || isActive;
          const showSources =
            turn.sources.length > 0 && Boolean(turn.answer.trim()) && !isActive;
          const showFollowUps =
            index === lastCompletedIndex &&
            turn.followUps.length > 0 &&
            !streaming &&
            !isActive;

          return (
            <article key={turn.key} className="thread-turn">
              <div className="thread-query">
                <p className="thread-query-text">{turn.query}</p>
              </div>

              {showStatus && (
                <SearchStatusLine phase={searchPhase} needsSearch={needsSearch} />
              )}

              {showAnswer && (
                <section className="answer-section">
                  <StreamingText text={turn.answer} streaming={isActive && streaming} />
                  {!isActive && turn.answer.trim() && (
                    <AnswerToolbar answer={turn.answer} title={turn.query} />
                  )}
                </section>
              )}

              {showSources && <SourcesCollapsible sources={turn.sources} />}

              {showFollowUps && (
                <section className="followups-section">
                  <div className="section-title">{t("followUps")}</div>
                  <div className="chips">
                    {turn.followUps.map((q) => (
                      <button
                        key={q}
                        type="button"
                        className="chip"
                        disabled={streaming}
                        onClick={() => runSearch(q, threadId, [])}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </article>
          );
        })}
        <div ref={scrollBottomRef} className="thread-scroll-anchor" aria-hidden />
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
