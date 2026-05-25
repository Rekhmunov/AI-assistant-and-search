import { useEffect, useState } from "react";

const TYPE_MS = 42;
const PAUSE_MS = 3000;
const BETWEEN_MS = 280;

/** Печатающийся placeholder: набор символов → пауза → следующая фраза. */
export function useTypingPlaceholder(enabled: boolean, phrases: readonly string[]): string {
  const [text, setText] = useState("");

  useEffect(() => {
    if (!enabled || phrases.length === 0) {
      setText("");
      return;
    }

    let cancelled = false;
    let timeoutId = 0;
    let phraseIndex = 0;
    let charIndex = 0;

    const schedule = (ms: number, fn: () => void) => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(fn, ms);
    };

    const startPhrase = () => {
      charIndex = 0;
      setText("");
      schedule(BETWEEN_MS, typeTick);
    };

    const nextPhrase = () => {
      phraseIndex = (phraseIndex + 1) % phrases.length;
      startPhrase();
    };

    const typeTick = () => {
      if (cancelled) return;
      const phrase = phrases[phraseIndex] ?? "";
      if (charIndex < phrase.length) {
        charIndex += 1;
        setText(phrase.slice(0, charIndex));
        schedule(TYPE_MS, typeTick);
        return;
      }
      schedule(PAUSE_MS, nextPhrase);
    };

    startPhrase();

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [enabled, phrases.join("\u0000")]);

  return text;
}
