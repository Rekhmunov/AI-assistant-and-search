import { useEffect, useRef, useState } from "react";

const TICK_MS = 16;

/** Ровный темп «печати» (~2–3 символа за тик ≈ 120–180 символов/с). */
function charsPerTick(lag: number): number {
  if (lag > 800) return 4;
  if (lag > 200) return 3;
  return 2;
}

export type StreamingRevealState = {
  text: string;
  /** Идёт набор символов (включая догон после окончания SSE). */
  isTyping: boolean;
};

/**
 * Показывает текст с эффектом набора при стриме (как в Perplexity).
 * После SSE продолжает печатать до полного текста — без мгновенного «догона».
 */
export function useStreamingReveal(fullText: string, isStreaming: boolean): StreamingRevealState {
  const [shown, setShown] = useState(() => (isStreaming ? "" : fullText));
  const fullRef = useRef(fullText);
  const shownRef = useRef(shown);
  fullRef.current = fullText;
  shownRef.current = shown;

  const isTyping = isStreaming || shown.length < fullText.length;

  useEffect(() => {
    if (!isStreaming) return;
    setShown((prev) => (fullText.startsWith(prev) ? prev : ""));
  }, [isStreaming, fullText]);

  useEffect(() => {
    const tick = () => {
      setShown((prev) => {
        const target = fullRef.current;
        if (prev.length >= target.length) return prev;
        const step = charsPerTick(target.length - prev.length);
        return target.slice(0, Math.min(target.length, prev.length + step));
      });
    };

    if (!isStreaming && shownRef.current.length >= fullRef.current.length) {
      return;
    }

    tick();
    const id = window.setInterval(tick, TICK_MS);
    return () => clearInterval(id);
  }, [isStreaming, fullText]);

  return { text: shown, isTyping };
}
