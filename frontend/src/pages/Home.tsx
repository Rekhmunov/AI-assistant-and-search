import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createAgentThread, fetchSession } from "../api/client";
import { GlosixBrand } from "../components/GlosixBrand";
import { HomeMobileHeader } from "../components/HomeMobileHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { getHomePlaceholderPhrases } from "../constants/homePlaceholders";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useAuthStore } from "../store/authStore";

export function Home() {
  const navigate = useNavigate();
  const isDesktop = useDesktopLayout();
  const token = useAuthStore((s) => s.token);
  const userPlan = useAuthStore((s) => s.user?.plan);
  const brandTier = userPlan === "pro" ? "pro" : "free";
  const [query, setQuery] = useState("");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [agentError, setAgentError] = useState<string | null>(null);

  const { data: session } = useQuery({
    queryKey: ["session", token],
    queryFn: () => fetchSession(token),
  });

  const startSearch = (payload: {
    query: string;
    attachmentIds: string[];
    attachments: ComposerAttachment[];
  }) => {
    if (!payload.query.trim() && payload.attachmentIds.length > 0) {
      return;
    }
    const params = new URLSearchParams();
    params.set("q", payload.query);
    if (payload.attachmentIds.length) {
      params.set("files", payload.attachmentIds.join(","));
    }
    const pendingAttachments = payload.attachments.map((a) => ({
      id: a.id,
      filename: a.filename,
      kind: a.kind,
      previewUrl: a.previewUrl,
    }));
    navigate(`/thread?${params.toString()}`, {
      state: pendingAttachments.length ? { pendingAttachments } : undefined,
    });
  };

  const createAgent = useMutation({
    mutationFn: () => createAgentThread(token),
    onSuccess: (data) => {
      setAgentError(null);
      navigate(`/thread/${data.thread.id}`, {
        state: { fromHistory: true, agentRevealWelcome: true },
      });
    },
    onError: (err) => {
      setAgentError(
        err instanceof Error ? err.message : "Не удалось создать агента. Попробуйте ещё раз.",
      );
    },
  });

  const startAgent = () => {
    if (createAgent.isPending) return;
    const canStart = Boolean(token) || session?.authenticated === true;
    if (!canStart) return;
    setAgentError(null);
    createAgent.mutate();
  };

  const hasDraft = Boolean(query.trim() || attachments.length > 0);
  const placeholderPhrases = useMemo(() => getHomePlaceholderPhrases(), []);

  return (
    <div className={`page page-home${isDesktop ? "" : " page-home--mobile"}`}>
      {!isDesktop && <HomeMobileHeader />}
      {isDesktop ? (
        <SearchComposer
          value={query}
          onChange={setQuery}
          onSubmit={startSearch}
          attachments={attachments}
          onAttachmentsChange={setAttachments}
          docked={false}
          animatedPlaceholder={!hasDraft}
          placeholderPhrases={placeholderPhrases}
          requireTextWithAttachments
          onAgentClick={startAgent}
          agentStarting={createAgent.isPending}
          agentError={agentError}
        />
      ) : (
        <div className="home-mobile-main">
          <div className="home-mobile-center-stack">
            <div className="home-mobile-brand-wrap">
              <GlosixBrand asLink={false} className="home-mobile-brand" tier={brandTier} />
            </div>
            <div className="home-mobile-composer-wrap">
              <SearchComposer
                value={query}
                onChange={setQuery}
                onSubmit={startSearch}
                attachments={attachments}
                onAttachmentsChange={setAttachments}
                docked={false}
                layoutMode="homeMobile"
                animatedPlaceholder={!hasDraft}
                placeholderPhrases={placeholderPhrases}
                requireTextWithAttachments
                onAgentClick={startAgent}
                agentStarting={createAgent.isPending}
                agentError={agentError}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
