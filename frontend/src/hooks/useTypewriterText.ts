import { useEffect, useState } from "react";

const CHAR_MS = 38;

/** Посимвольный набор одной строки; при смене target — с начала. */
export function useTypewriterText(
  target: string,
  active: boolean,
): { text: string; isTyping: boolean } {
  const [shown, setShown] = useState("");

  useEffect(() => {
    if (!active || !target) {
      setShown("");
      return;
    }

    let cancelled = false;
    let charIndex = 0;
    let timeoutId = 0;

    setShown("");

    const tick = () => {
      if (cancelled) return;
      if (charIndex < target.length) {
        charIndex += 1;
        setShown(target.slice(0, charIndex));
        timeoutId = window.setTimeout(tick, CHAR_MS);
      }
    };

    timeoutId = window.setTimeout(tick, CHAR_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [target, active]);

  const isTyping = active && shown.length < target.length;
  return { text: active ? shown : "", isTyping };
}
