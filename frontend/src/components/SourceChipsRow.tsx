import type { Source } from "../api/client";
import { faviconUrl } from "../lib/sourceDomainLabel";
import { groupSourcesForChips } from "../lib/sourceChipGroups";

type Props = {
  indices: number[];
  sources: Source[];
  className?: string;
};

export function SourceChipsRow({ indices, sources, className }: Props) {
  const groups = groupSourcesForChips(indices, sources);
  if (!groups.length) return null;

  return (
    <div className={className ?? "source-chips-row"}>
      {groups.map((group) => (
        <a
          key={`${group.label}-${group.url}`}
          href={group.url}
          target="_blank"
          rel="noopener noreferrer"
          className="source-chip"
          title={group.url}
        >
          <img
            className="source-chip-icon"
            src={faviconUrl(group.faviconDomain)}
            alt=""
            width={12}
            height={12}
            loading="lazy"
            decoding="async"
          />
          <span className="source-chip-label">
            {group.label}
            {group.extraCount > 0 && (
              <span className="source-chip-extra"> +{group.extraCount}</span>
            )}
          </span>
        </a>
      ))}
    </div>
  );
}
