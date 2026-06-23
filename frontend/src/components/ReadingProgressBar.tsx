import { useEffect, useState } from "react";

export function ReadingProgressBar() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      const el = document.documentElement;
      const scrollTop = window.scrollY;
      const docHeight = el.scrollHeight - el.clientHeight;
      if (docHeight <= 0) { setProgress(0); return; }
      setProgress(Math.min(100, Math.round((scrollTop / docHeight) * 100)));
    };
    window.addEventListener("scroll", update, { passive: true });
    update();
    return () => window.removeEventListener("scroll", update);
  }, []);

  if (progress <= 0) return null;

  return (
    <div
      className="reading-progress-bar"
      role="progressbar"
      aria-valuenow={progress}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Прогресс чтения"
    >
      <div className="reading-progress-bar__fill" style={{ width: `${progress}%` }} />
    </div>
  );
}
