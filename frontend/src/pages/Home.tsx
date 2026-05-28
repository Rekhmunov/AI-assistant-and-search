import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { getHomePlaceholderPhrases } from "../constants/homePlaceholders";

export function Home() {
  const navigate = useNavigate();
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
    <div className="page page-home">
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
    </div>
  );
}
