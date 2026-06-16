import { useEffect, useState } from "react";
import { useTypewriterText } from "./useTypewriterText";

type Options = {
  /** Пауза после полного набора строки, мс */
  holdMs?: number;
  /**
   * Если true — останавливается на последнем сообщении и не зацикливается.
   * Используется для генерации изображений, чтобы последний статус держался
   * до конца операции.
   */
  stopAtLast?: boolean;
};

/** По очереди печатает статусы; после паузы переходит к следующей. */
export function useRotatingTypewriterStatus(
  messages: string[],
  active: boolean,
  options?: Options,
): { text: string; isTyping: boolean; label: string } {
  const holdMs = options?.holdMs ?? 2400;
  const stopAtLast = options?.stopAtLast ?? false;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) setIndex(0);
  }, [active]);

  const safeMessages = messages.filter((m) => m.trim().length > 0);
  const clampedIndex = stopAtLast
    ? Math.min(index, safeMessages.length - 1)
    : index % Math.max(safeMessages.length, 1);
  const current = safeMessages.length ? safeMessages[clampedIndex] : "";
  const { text, isTyping } = useTypewriterText(current, active && Boolean(current));

  useEffect(() => {
    if (!active || isTyping || safeMessages.length < 2) return;
    if (stopAtLast && clampedIndex >= safeMessages.length - 1) return;
    const id = window.setTimeout(() => {
      setIndex((i) => i + 1);
    }, holdMs);
    return () => window.clearTimeout(id);
  }, [active, isTyping, current, safeMessages.length, holdMs, stopAtLast, clampedIndex]);

  return { text, isTyping, label: current };
}
