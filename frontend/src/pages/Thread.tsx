import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  fetchThread,
  saveThread,
  streamSearch,
  type Source,
} from "../api/client";
import { AnswerToolbar } from "../components/AnswerToolbar";
import { GlosixHeader } from "../components/GlosixHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SearchStatusLine, type SearchPhase } from "../components/SearchStatusLine";
import { SourcesCollapsible } from "../components/SourcesCollapsible";
import { StreamingText } from "../components/StreamingText";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

export function Thread() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const initialFiles = searchParams.get("files")?.split(",").filter(Boolean) ?? [];
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();

  const [threadId, setThreadId] = useState<string | null>(id ?? null);
  const [displayQuery, setDisplayQuery] = useState(initialQuery);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [answer, setAnswer] = useState("");
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [needsSearch, setNeedsSearch] = useState(true);
  const [searchPhase, setSearchPhase] = useState<SearchPhase>("idle");
  const [composerQuery, setComposerQuery] = useState("");
  const started = useRef(false);

  const { data: thread } = useQuery({
    queryKey: ["thread", id],
    queryFn: () => fetchThread(token, id!),
    enabled: !!id,
  });

  useEffect(() => {
    if (thread) {
      setSaved(thread.is_saved);
      const lastUser = [...thread.messages].reverse().find((m) => m.role === "user");
      if (lastUser) setDisplayQuery(lastUser.content);
      const lastAssistant = [...thread.messages].reverse().find((m) => m.role === "assistant");
      if (lastAssistant) {
        setAnswer(lastAssistant.content);
        setSources(lastAssistant.sources ?? []);
        setFollowUps(lastAssistant.follow_up_questions ?? []);
        setSearchPhase("idle");
      }
    }
  }, [thread]);

  const runSearch = useCallback(
    async (text: string, existingThreadId: string | null, attachmentIds: string[]) => {
      if (!text.trim() && !attachmentIds.length) return;
      if (streaming) return;
      setStreaming(true);
      setDisplayQuery(text);
      setAnswer("");
      setSources([]);
      setFollowUps([]);
      setSearchPhase("routing");

      await streamSearch(token, text, existingThreadId, attachmentIds, {
        onThread: (tid) => {
          setThreadId(tid);
          if (!id) navigate(`/thread/${tid}`, { replace: true });
        },
        onRoute: (route) => {
          setNeedsSearch(route.needs_search);
          setSearchPhase(route.needs_search ? "searching" : "answering");
        },
        onSources: (list) => {
          setSources(list);
          setSearchPhase("answering");
        },
        onToken: (chunk) => {
          setSearchPhase("answering");
          setAnswer((a) => a + chunk);
        },
        onFollowUps: setFollowUps,
        onDone: () => {
          setStreaming(false);
          setSearchPhase("idle");
          queryClient.invalidateQueries({ queryKey: ["session"] });
          queryClient.invalidateQueries({ queryKey: ["threads"] });
          if (threadId) queryClient.invalidateQueries({ queryKey: ["thread", threadId] });
        },
        onError: (msg) => {
          setStreaming(false);
          setSearchPhase("idle");
          setAnswer(msg);
        },
      });
    },
    [token, streaming, id, navigate, queryClient, threadId]
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

  const showStatus = streaming && !answer.trim();
  const showSources = sources.length > 0 && Boolean(answer.trim()) && !streaming;

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

      {displayQuery && (
        <div className="thread-query">
          <p className="thread-query-text">{displayQuery}</p>
        </div>
      )}

      {showStatus && <SearchStatusLine phase={searchPhase} needsSearch={needsSearch} />}

      {answer.trim() && (
        <section className="answer-section">
          <StreamingText text={answer} streaming={streaming} />
          {!streaming && answer.trim() && (
            <AnswerToolbar answer={answer} title={displayQuery} />
          )}
        </section>
      )}

      {showSources && <SourcesCollapsible sources={sources} />}

      {followUps.length > 0 && !streaming && (
        <section className="followups-section">
          <div className="section-title">{t("followUps")}</div>
          <div className="chips">
            {followUps.map((q) => (
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
