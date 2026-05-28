import { useEffect, useRef, useState } from "react";

const TICK_MS = 16;

/**
 * Скорость «печати»: во время SSE — ровный темп; после окончания стрима — чуть быстрее,
 * но с ограничением за тик, чтобы не было скачка всего абзаца за один кадр.
 */
function charsPerTick(lag: number, isStreaming: boolean): number {
  if (lag <= 0) return 0;
  if (isStreaming) {
    if (lag > 2000) return 10;
    if (lag > 800) return 6;
    if (lag > 200) return 4;
    return 2;
  }
  // Догон после SSE: быстрее, но плавно (не более ~30 символов за кадр).
  return Math.min(30, Math.max(4, Math.ceil(lag / 20)));
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
  const streamingRef = useRef(isStreaming);
  fullRef.current = fullText;
  shownRef.current = shown;
  streamingRef.current = isStreaming;

  const isTyping = isStreaming || shown.length < fullText.length;

  useEffect(() => {
    if (!isStreaming) return;
    setShown((prev) => {
      if (fullText.startsWith(prev)) return prev;
      if (prev.startsWith(fullText)) return fullText.slice(0, prev.length);
      return "";
    });
  }, [isStreaming, fullText]);

  useEffect(() => {
    const tick = () => {
      setShown((prev) => {
        const target = fullRef.current;
        if (prev.length >= target.length) return prev;
        const lag = target.length - prev.length;
        const step = charsPerTick(lag, streamingRef.current);
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
