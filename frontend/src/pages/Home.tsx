import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GlosixHeader } from "../components/GlosixHeader";
import { SearchComposer, type ComposerAttachment } from "../components/SearchComposer";
import { t } from "../i18n";

const SUGGESTIONS = ["Технологии", "Бизнес", "Наука", "Анализ Excel-отчёта"];

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

  return (
    <div className="page page-home">
      <GlosixHeader showBrand={false} />
      <div className="home-hero">
        <h1 className="home-title">{t("homeTitle")}</h1>
        <p className="home-subtitle">{t("homeSubtitle")}</p>
      </div>
      <div className="home-suggestions">
        {SUGGESTIONS.map((topic) => (
          <button key={topic} type="button" className="chip" onClick={() => setQuery(topic)}>
            {topic}
          </button>
        ))}
      </div>
      <SearchComposer
        value={query}
        onChange={setQuery}
        onSubmit={startSearch}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
      />
    </div>
  );
}
