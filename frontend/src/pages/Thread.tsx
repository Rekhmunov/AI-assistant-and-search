import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  fetchThread,
  saveThread,
  streamSearch,
  type Message,
  type Source,
} from "../api/client";
import { GlosixHeader } from "../components/GlosixHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { SourceCard } from "../components/SourceCard";
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
  const [query, setQuery] = useState(initialQuery);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [answer, setAnswer] = useState("");
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [routeLabel, setRouteLabel] = useState<string | null>(null);
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
      if (lastUser) setQuery(lastUser.content);
      const lastAssistant = [...thread.messages].reverse().find((m) => m.role === "assistant");
      if (lastAssistant) {
        setAnswer(lastAssistant.content);
        setSources(lastAssistant.sources ?? []);
        setFollowUps(lastAssistant.follow_up_questions ?? []);
      }
    }
  }, [thread]);

  const runSearch = useCallback(
    async (text: string, existingThreadId: string | null, attachmentIds: string[]) => {
      if (!text.trim() && !attachmentIds.length) return;
      if (streaming) return;
      setStreaming(true);
      setAnswer("");
      setSources([]);
      setFollowUps([]);
      setRouteLabel(null);

      await streamSearch(token, text, existingThreadId, attachmentIds, {
        onThread: (tid) => {
          setThreadId(tid);
          if (!id) navigate(`/thread/${tid}`, { replace: true });
        },
        onRoute: (route) => {
          if (route.needs_search) {
            setRouteLabel(
              route.answer_model === "pro" ? t("routeSearchPro") : t("routeSearchLite")
            );
          } else {
            setRouteLabel(t("routeDirect"));
          }
        },
        onSources: setSources,
        onToken: (chunk) => setAnswer((a) => a + chunk),
        onFollowUps: setFollowUps,
        onDone: () => {
          setStreaming(false);
          queryClient.invalidateQueries({ queryKey: ["session"] });
          queryClient.invalidateQueries({ queryKey: ["threads"] });
          if (threadId) queryClient.invalidateQueries({ queryKey: ["thread", threadId] });
        },
        onError: (msg) => {
          setStreaming(false);
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
    setQuery(payload.query);
    runSearch(payload.query, threadId, payload.attachmentIds);
  };

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

      {query && (
        <div className="query-box">
          <span className="query-label">{t("queryLabel")}</span>
          <p className="query-text">{query}</p>
          {routeLabel && <span className="route-badge">{routeLabel}</span>}
        </div>
      )}

      {sources.length > 0 && (
        <section className="sources-section">
          <div className="section-title">{t("sources")}</div>
          <div className="source-carousel">
            {sources.map((s) => (
              <SourceCard key={s.index} source={s} />
            ))}
          </div>
        </section>
      )}

      <StreamingText text={answer || (streaming ? t("loading") : "")} streaming={streaming} />

      {followUps.length > 0 && (
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
        value={query}
        onChange={setQuery}
        onSubmit={onComposerSubmit}
        disabled={streaming}
        placeholder={t("askFollowUp")}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
      />
    </div>
  );
}
