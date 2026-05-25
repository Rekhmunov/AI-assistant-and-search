import { useCallback, useRef, useState } from "react";

type VoiceState = "idle" | "recording" | "transcribing";

/** Browser speech recognition when available; otherwise returns null. */
export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setState("idle");
  }, []);

  const start = useCallback(() => {
    setError(null);
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      setError("Голос недоступен в этом браузере. Введите текст вручную.");
      return;
    }
    const rec = new SR();
    rec.lang = "ru-RU";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    recognitionRef.current = rec;
    setState("recording");

    rec.onresult = (ev: SpeechRecognitionEvent) => {
      const text = ev.results[0]?.[0]?.transcript?.trim();
      if (text) onText(text);
      setState("idle");
    };
    rec.onerror = () => {
      setError("Не удалось распознать речь");
      setState("idle");
    };
    rec.onend = () => {
      if (state === "recording") setState("idle");
    };
    rec.start();
  }, [onText, state]);

  const toggle = useCallback(() => {
    if (state === "recording") {
      stop();
      setState("transcribing");
      setTimeout(() => setState("idle"), 300);
    } else {
      start();
    }
  }, [state, start, stop]);

  return { state, error, toggle, stop };
}
