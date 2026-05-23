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
import { SearchBar } from "../components/SearchBar";
import { SourceCard } from "../components/SourceCard";
import { StreamingText } from "../components/StreamingText";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

export function Thread() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token)!;
  const queryClient = useQueryClient();

  const [threadId, setThreadId] = useState<string | null>(id ?? null);
  const [query, setQuery] = useState(initialQuery);
  const [followUp, setFollowUp] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [answer, setAnswer] = useState("");
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [saved, setSaved] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const started = useRef(false);

  const { data: thread } = useQuery({
    queryKey: ["thread", id],
    queryFn: () => fetchThread(token, id!),
    enabled: !!id && !!token,
  });

  useEffect(() => {
    if (thread) {
      setSaved(thread.is_saved);
      setMessages(thread.messages);
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
    async (text: string, existingThreadId: string | null) => {
      if (!text.trim() || streaming) return;
      setStreaming(true);
      setAnswer("");
      setSources([]);
      setFollowUps([]);

      await streamSearch(token, text, existingThreadId, {
        onThread: (tid) => {
          setThreadId(tid);
          if (!id) navigate(`/thread/${tid}`, { replace: true });
        },
        onSources: setSources,
        onToken: (chunk) => setAnswer((a) => a + chunk),
        onFollowUps: setFollowUps,
        onDone: () => {
          setStreaming(false);
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
    if (initialQuery && !id && !started.current && token) {
      started.current = true;
      runSearch(initialQuery, null);
    }
  }, [initialQuery, id, token, runSearch]);

  const handleSave = async () => {
    if (!threadId) return;
    await saveThread(token, threadId);
    setSaved(true);
  };

  const submitFollowUp = () => {
    const text = followUp.trim();
    if (!text) return;
    setFollowUp("");
    setMessages((m) => [
      ...m,
      { id: "tmp-u", role: "user", content: text, sources: null, follow_up_questions: null, created_at: new Date().toISOString() },
    ]);
    runSearch(text, threadId);
  };

  return (
    <div className="page">
      <div className="thread-header">
        <button type="button" className="icon-btn" onClick={() => navigate(-1)}>
          ← {t("back")}
        </button>
        <button type="button" className="icon-btn" onClick={handleSave} disabled={!threadId || saved}>
          💾 {saved ? t("saved") : t("save")}
        </button>
      </div>

      <div className="query-box">
        {t("queryLabel")}: &quot;{query}&quot;
      </div>

      {sources.length > 0 && (
        <>
          <div className="section-title">{t("sources")}</div>
          <div className="source-cards">
            {sources.map((s) => (
              <SourceCard key={s.index} source={s} />
            ))}
          </div>
        </>
      )}

      <StreamingText text={answer || (streaming ? t("loading") : "")} streaming={streaming} />

      {messages.map((m) =>
        m.id.startsWith("tmp") ? null : (
          <div key={m.id} style={{ display: "none" }} />
        )
      )}

      {followUps.length > 0 && (
        <>
          <div className="section-title">{t("followUps")}</div>
          <ul className="follow-up-list">
            {followUps.map((q) => (
              <li
                key={q}
                onClick={() => {
                  setFollowUp(q);
                  runSearch(q, threadId);
                }}
              >
                {q}
              </li>
            ))}
          </ul>
        </>
      )}

      <SearchBar
        value={followUp}
        onChange={setFollowUp}
        onSubmit={submitFollowUp}
        placeholder={t("askFollowUp")}
      />
    </div>
  );
}
