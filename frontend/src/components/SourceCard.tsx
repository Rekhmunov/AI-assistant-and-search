import type { Source } from "../api/client";

export function SourceCard({ source }: { source: Source }) {
  return (
    <a className="source-card" href={source.url} target="_blank" rel="noreferrer">
      <strong>{source.domain}</strong>
      <span>{source.title}</span>
    </a>
  );
}
