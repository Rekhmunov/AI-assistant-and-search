import type { Source } from "../api/client";

import { SourceLink } from "./SourceLink";

export function SourceCard({ source }: { source: Source }) {
  return (
    <SourceLink className="source-card" href={source.url}>
      <strong>{source.domain}</strong>
      <span>{source.title}</span>
    </SourceLink>
  );
}
