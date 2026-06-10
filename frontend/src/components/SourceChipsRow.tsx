import type { Source } from "../api/client";
import { SourceLink } from "./SourceLink";
import { faviconUrl } from "../lib/sourceDomainLabel";
import { groupSourcesForChips } from "../lib/sourceChipGroups";

type Props = {
  indices: number[];
  sources: Source[];
  className?: string;
  /** Favicon только в футере «N источников»; в тексте ответа — без иконок */
  showFavicon?: boolean;
};

export function SourceChipsRow({ indices, sources, className, showFavicon = false }: Props) {
  const groups = groupSourcesForChips(indices, sources);
  if (!groups.length) return null;

  return (
    <span className={className ?? "source-chips-row"}>
      {groups.map((group) => (
        <SourceLink
          key={`${group.label}-${group.url}`}
          href={group.url}
          className="source-chip"
          title={group.url}
        >
          {showFavicon && (
            <img
              className="source-chip-icon"
              src={faviconUrl(group.faviconDomain)}
              alt=""
              width={12}
              height={12}
              loading="lazy"
              decoding="async"
            />
          )}
          <span className="source-chip-label">
            {group.label}
            {group.extraCount > 0 && (
              <span className="source-chip-extra"> +{group.extraCount}</span>
            )}
          </span>
        </SourceLink>
      ))}
    </span>
  );
}
