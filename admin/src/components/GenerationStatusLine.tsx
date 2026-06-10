import { useEffect, useMemo, useState } from "react";

const CHAR_MS = 38;

const DEFAULT_MESSAGES = [
  "Запускаем генерацию…",
  "Делаем шедевр…",
  "Смешиваем краски…",
  "Почти готово…",
  "Дорисовываем детали…",
];

type Props = {
  active: boolean;
  status?: string;
};

function useTypewriterText(target: string, active: boolean): { text: string; isTyping: boolean } {
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

  return { text: active ? shown : "", isTyping: active && shown.length < target.length };
}

function useRotatingStatus(messages: string[], active: boolean): { text: string; isTyping: boolean; label: string } {
  const holdMs = 4400;
  const [index, setIndex] = useState(0);
  const safeMessages = messages.filter((m) => m.trim().length > 0);
  const current = safeMessages.length ? safeMessages[index % safeMessages.length] : "";
  const { text, isTyping } = useTypewriterText(current, active && Boolean(current));

  useEffect(() => {
    if (!active) setIndex(0);
  }, [active]);

  useEffect(() => {
    if (!active || isTyping || safeMessages.length < 2) return;
    const id = window.setTimeout(() => {
      setIndex((i) => (i + 1) % safeMessages.length);
    }, holdMs);
    return () => window.clearTimeout(id);
  }, [active, isTyping, current, safeMessages.length]);

  return { text, isTyping, label: current };
}

export function GenerationStatusLine({ active, status }: Props) {
  const messages = useMemo(() => {
    const fromServer = status?.trim();
    if (!fromServer) return DEFAULT_MESSAGES;
    if (DEFAULT_MESSAGES.includes(fromServer)) return DEFAULT_MESSAGES;
    return [fromServer, ...DEFAULT_MESSAGES];
  }, [status]);

  const { text, isTyping, label } = useRotatingStatus(messages, active);
  if (!active) return null;

  return (
    <div className="blog-gen-status" role="status" aria-live="polite" aria-label={label}>
      <span className="blog-gen-status-dot" />
      <span className={`blog-gen-status-text${isTyping ? " blog-gen-status-text--typing" : ""}`}>
        {text}
      </span>
    </div>
  );
}
