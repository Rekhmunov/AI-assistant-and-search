import { useEffect } from "react";
import { createPortal } from "react-dom";

type Props = {
  message: string;
  onDone: () => void;
  durationMs?: number;
};

export function SupportToast({ message, onDone, durationMs = 2800 }: Props) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, durationMs);
    return () => window.clearTimeout(timer);
  }, [durationMs, onDone]);

  return createPortal(
    <div className="feedback-thank-toast" role="status" aria-live="polite">
      <p>{message}</p>
    </div>,
    document.body,
  );
}
