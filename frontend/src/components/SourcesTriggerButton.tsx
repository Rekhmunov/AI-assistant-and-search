import type { Source } from "../api/client";
import { sourcesCountLabel } from "../lib/sourcesCountLabel";
import { SourceFaviconStack } from "./SourceFaviconStack";

type Props = {
  sources: Source[];
  onClick: () => void;
};

export function SourcesTriggerButton({ sources, onClick }: Props) {
  const { count, word } = sourcesCountLabel(sources.length);

  return (
    <button type="button" className="sources-trigger" onClick={onClick} aria-haspopup="dialog">
      <SourceFaviconStack sources={sources} max={3} size="sm" />
      <span className="sources-trigger-label">
        <span className="sources-trigger-count">{count}</span>
        <span className="sources-trigger-word">{word}</span>
      </span>
    </button>
  );
}
