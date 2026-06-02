import type { EntityImage } from "../api/client";
import type { ThreadTurn } from "./threadTurns";

export type ThreadImageGroup = {
  turnKey: string;
  query: string;
  images: EntityImage[];
};

/** Группы изображений по вопросам: новые turn сверху. */
export function buildThreadImageGroups(turns: ThreadTurn[]): ThreadImageGroup[] {
  const groups: ThreadImageGroup[] = [];

  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turn = turns[i];
    const images = turn.images ?? [];
    if (!images.length) continue;
    groups.push({
      turnKey: turn.key,
      query: turn.query,
      images,
    });
  }

  return groups;
}

export function countThreadImages(turns: ThreadTurn[]): number {
  return turns.reduce((sum, turn) => sum + (turn.images?.length ?? 0), 0);
}

export function threadHasSearchTurns(turns: ThreadTurn[]): boolean {
  return turns.some(
    (turn) =>
      (turn.images?.length ?? 0) > 0 ||
      turn.needsSearch === true ||
      (turn.needsSearch == null && (turn.sources?.length ?? 0) > 0),
  );
}
