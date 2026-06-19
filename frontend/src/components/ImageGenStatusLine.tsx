import { useMemo, useState, useEffect } from "react";
import { useRotatingTypewriterStatus } from "../hooks/useRotatingTypewriterStatus";
import { t } from "../i18n";

type Props = {
  active: boolean;
  /** Статус из SSE (GigaChat text2image). */
  status?: string;
};

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

  // Первый статус показываем сразу (без typewriter-задержки) — чтобы не было
  // пустого экрана пока typewriter «разгоняется» после LLM-роутера (~1-2с).
  // После первой смены статуса включается обычный typewriter-эффект.
  const [firstDone, setFirstDone] = useState(false);
  useEffect(() => {
    if (!active) {
      setFirstDone(false);
      return;
    }
    const id = setTimeout(() => setFirstDone(true), 4400);
    return () => clearTimeout(id);
  }, [active]);

  const { text, isTyping, label } = useRotatingTypewriterStatus(messages, active, {
    holdMs: 4400,
    stopAtLast: true,
  });

  if (!active) return null;

  // До окончания первого интервала — показываем первое сообщение целиком
  // (без посимвольной анимации); потом typewriter включается для следующих.
  const displayText = firstDone ? text : (messages[0] ?? text);
  const displayTyping = firstDone ? isTyping : false;

  return (
    <div className="search-status" role="status" aria-live="polite" aria-label={label}>
      <span className="search-status-dot" />
      <span
        className={`search-status-text${displayTyping ? " search-status-text--typing" : ""}`}
        aria-hidden={displayTyping}
      >
        {displayText}
      </span>
    </div>
  );
}
