import { useEffect, useRef, useState, useMemo } from "react";
import { t } from "../i18n";

type Props = {
  active: boolean;
  /** Статус из SSE (GigaChat text2image). */
  status?: string;
};

const HOLD_MS = 4000;

export function ImageGenStatusLine({ active, status }: Props) {
  const messages = useMemo(() => {
    const base = [
      t("imageGenStatus1"),
      t("imageGenStatus2"),
      t("imageGenStatus3"),
      t("imageGenStatus4"),
      t("imageGenStatus5"),
    ];
    const fromServer = status?.trim();
    if (!fromServer) return base;
    if (base.includes(fromServer)) return base;
    return [fromServer, ...base];
  }, [status]);

  const [index, setIndex] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!active) {
      setIndex(0);
      return;
    }
    // Показываем первый статус немедленно, потом меняем каждые HOLD_MS
    const schedule = () => {
      timer.current = setTimeout(() => {
        setIndex((i) => {
          const next = i + 1;
          if (next >= messages.length) return i; // stopAtLast
          schedule();
          return next;
        });
      }, HOLD_MS);
    };
    schedule();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [active, messages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!active) return null;

  const text = messages[Math.min(index, messages.length - 1)] ?? "";

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={text}>
      <span className="search-status-dot" />
      <span className="search-status-text">{text}</span>
    </div>
  );
}
