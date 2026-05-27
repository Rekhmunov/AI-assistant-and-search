import { useEffect, useRef, useState } from "react";

const TICK_MS = 20;

/** Скорость «печати» (символов за тик); при отставании от SSE ускоряем. */
function charsPerTick(lag: number): number {
  if (lag > 400) return 14;
  if (lag > 150) return 8;
  if (lag > 50) return 4;
  return 2;
}

/**
 * Показывает текст с эффектом набора при стриме (как в Perplexity).
 * Когда стрим завершён — сразу полный текст.
 */
export function useStreamingReveal(fullText: string, isStreaming: boolean): string {
  const [shown, setShown] = useState(isStreaming ? "" : fullText);
  const fullRef = useRef(fullText);
  fullRef.current = fullText;

  useEffect(() => {
    if (!isStreaming) {
      setShown(fullText);
      return;
    }

    setShown((prev) => (fullText.startsWith(prev) ? prev : ""));

    const id = window.setInterval(() => {
      setShown((prev) => {
        const target = fullRef.current;
        if (prev.length >= target.length) return prev;
        const step = charsPerTick(target.length - prev.length);
        return target.slice(0, Math.min(target.length, prev.length + step));
      });
    }, TICK_MS);

    return () => clearInterval(id);
  }, [isStreaming, fullText]);

  return shown;
}
