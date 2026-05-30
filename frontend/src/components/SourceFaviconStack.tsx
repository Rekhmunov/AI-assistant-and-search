import type { Source } from "../api/client";
import { faviconUrl } from "../lib/sourceDomainLabel";

type Props = {
  sources: Source[];
  max?: number;
  size?: "sm" | "md";
};

export function SourceFaviconStack({ sources, max = 3, size = "md" }: Props) {
  const items = sources.slice(0, max);
  if (!items.length) return null;

  return (
    <span className={`source-favicon-stack source-favicon-stack--${size}`} aria-hidden>
      {items.map((source, index) => (
        <span
          key={source.index}
          className="source-favicon-stack-item"
          style={{ zIndex: items.length - index }}
        >
          <img
            src={faviconUrl(source.domain || source.url)}
            alt=""
            width={size === "sm" ? 18 : 22}
            height={size === "sm" ? 18 : 22}
            loading="lazy"
            decoding="async"
          />
        </span>
      ))}
    </span>
  );
}
