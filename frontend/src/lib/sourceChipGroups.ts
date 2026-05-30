import type { Source } from "../api/client";
import { sourceDomainLabel, sourceFaviconDomain } from "./sourceDomainLabel";

export type SourceChipGroup = {
  label: string;
  faviconDomain: string;
  url: string;
  extraCount: number;
};

export function groupSourcesForChips(indices: number[], sources: Source[]): SourceChipGroup[] {
  const byIndex = new Map(sources.map((s) => [s.index, s]));
  const groups = new Map<string, SourceChipGroup>();

  for (const index of indices) {
    const src = byIndex.get(index);
    if (!src?.url) continue;

    const label = sourceDomainLabel(src.domain || src.url);
    if (!label) continue;

    const key = label.toLowerCase();
    const existing = groups.get(key);
    if (existing) {
      existing.extraCount += 1;
      continue;
    }

    groups.set(key, {
      label,
      faviconDomain: sourceFaviconDomain(src.domain || src.url),
      url: src.url,
      extraCount: 0,
    });
  }

  return [...groups.values()];
}
