import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GlosixBrand } from "../components/GlosixBrand";
import { HomeMobileHeader } from "../components/HomeMobileHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { getHomePlaceholderPhrases } from "../constants/homePlaceholders";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useAuthStore } from "../store/authStore";

export function Home() {
  const navigate = useNavigate();
  const isDesktop = useDesktopLayout();
  const userPlan = useAuthStore((s) => s.user?.plan);
  const brandTier = userPlan === "pro" ? "pro" : "free";
  const [query, setQuery] = useState("");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);

  const startSearch = (payload: { query: string; attachmentIds: string[] }) => {
    if (!payload.query.trim() && payload.attachmentIds.length > 0) {
      return;
    }
    const params = new URLSearchParams();
    params.set("q", payload.query);
    if (payload.attachmentIds.length) {
      params.set("files", payload.attachmentIds.join(","));
    }
    navigate(`/thread?${params.toString()}`);
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
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
