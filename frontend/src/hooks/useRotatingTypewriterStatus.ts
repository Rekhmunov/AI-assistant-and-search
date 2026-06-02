import { useEffect, useState } from "react";
import { useTypewriterText } from "./useTypewriterText";

type Options = {
  /** Пауза после полного набора строки, мс */
  holdMs?: number;
};

/** По очереди печатает статусы; после паузы переходит к следующей. */
export function useRotatingTypewriterStatus(
  messages: string[],
  active: boolean,
  options?: Options,
): { text: string; isTyping: boolean; label: string } {
  const holdMs = options?.holdMs ?? 2400;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!active) setIndex(0);
  }, [active]);

  const safeMessages = messages.filter((m) => m.trim().length > 0);
  const current = safeMessages.length ? safeMessages[index % safeMessages.length] : "";
  const { text, isTyping } = useTypewriterText(current, active && Boolean(current));

  useEffect(() => {
    if (!active || isTyping || safeMessages.length < 2) return;
    const id = window.setTimeout(() => {
      setIndex((i) => (i + 1) % safeMessages.length);
    }, holdMs);
    return () => window.clearTimeout(id);
  }, [active, isTyping, current, safeMessages.length, holdMs]);

  return { text, isTyping, label: current };
}
