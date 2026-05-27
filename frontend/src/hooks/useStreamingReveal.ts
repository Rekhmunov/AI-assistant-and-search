import { useEffect, useRef, useState } from "react";

const TICK_MS = 20;

/** Ровный темп «печати»; при отставании слегка ускоряем, без скачка в конце. */
function charsPerTick(lag: number): number {
  if (lag > 600) return 5;
  if (lag > 120) return 3;
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
  fullRef.current = fullText;

  const isTyping = isStreaming || shown.length < fullText.length;

  useEffect(() => {
    if (!isStreaming) return;
    setShown((prev) => (fullText.startsWith(prev) ? prev : ""));
  }, [isStreaming, fullText]);

  useEffect(() => {
    if (!isStreaming && shown.length >= fullText.length) return;

    const id = window.setInterval(() => {
      setShown((prev) => {
        const target = fullRef.current;
        if (prev.length >= target.length) return prev;
        const step = charsPerTick(target.length - prev.length);
        return target.slice(0, Math.min(target.length, prev.length + step));
      });
    }, TICK_MS);

    return () => clearInterval(id);
  }, [isStreaming, fullText, shown.length]);

  return { text: shown, isTyping };
}
