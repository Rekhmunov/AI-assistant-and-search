import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GlosixHeader } from "../components/GlosixHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { getHomePlaceholderPhrases } from "../constants/homePlaceholders";

export function Home() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);

  const startSearch = (payload: { query: string; attachmentIds: string[] }) => {
    const params = new URLSearchParams();
    params.set("q", payload.query);
    if (payload.attachmentIds.length) {
      params.set("files", payload.attachmentIds.join(","));
    }
    navigate(`/thread?${params.toString()}`);
  };

  const composing = Boolean(query.trim() || attachments.length > 0);
  const placeholderPhrases = useMemo(() => getHomePlaceholderPhrases(), []);

  return (
    <div className={`page page-home${composing ? " page-home--composing" : ""}`}>
      <GlosixHeader showBrand={false} />
      <SearchComposer
        value={query}
        onChange={setQuery}
        onSubmit={startSearch}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        docked={composing}
        animatedPlaceholder={!composing}
        placeholderPhrases={placeholderPhrases}
      />
    </div>
  );
}
