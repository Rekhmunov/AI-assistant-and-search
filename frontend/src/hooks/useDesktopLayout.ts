import { useEffect, useState } from "react";

const DESKTOP_MQ = `(min-width: ${900}px)`;

/** Веб-версия с левым меню (без нижней навигации). */
export function useDesktopLayout(): boolean {
  const [desktop, setDesktop] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(DESKTOP_MQ).matches : false,
  );

  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_MQ);
    const onChange = () => setDesktop(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return desktop;
}
