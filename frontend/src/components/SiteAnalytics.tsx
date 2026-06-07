import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { fetchAppConfig } from "../api/client";

declare global {
  interface Window {
    ym?: (counterId: number, method: string, ...args: unknown[]) => void;
  }
}

type Props = {
  /** Загружать Метрику только после согласия на cookie */
  enabled: boolean;
};

function loadYandexMetrica(counterId: string): void {
  const id = Number(counterId);
  if (!Number.isFinite(id) || id <= 0) return;

  const tagUrl = "https://mc.yandex.ru/metrika/tag.js";
  for (const script of document.scripts) {
    if (script.src === tagUrl) return;
  }

  const w = window as Window & { ym?: { a?: unknown[]; l?: number } };
  w.ym =
    w.ym ||
    function (...args: unknown[]) {
      (w.ym!.a = w.ym!.a || []).push(args);
    };
  w.ym!.l = Date.now();

  const script = document.createElement("script");
  script.async = true;
  script.src = tagUrl;
  document.head.appendChild(script);

  window.ym?.(id, "init", {
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: true,
  });
}

export function SiteAnalytics({ enabled }: Props) {
  const loadedRef = useRef(false);
  const { data: config } = useQuery({
    queryKey: ["app-config"],
    queryFn: fetchAppConfig,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!enabled || loadedRef.current) return;
    const counterId = config?.yandex_metrica_counter_id?.trim();
    if (!counterId) return;
    loadedRef.current = true;
    loadYandexMetrica(counterId);
  }, [enabled, config?.yandex_metrica_counter_id]);

  const counterId = config?.yandex_metrica_counter_id?.trim();
  if (!enabled || !counterId) return null;

  const id = Number(counterId);
  if (!Number.isFinite(id) || id <= 0) return null;

  return (
    <noscript>
      <div>
        <img
          src={`https://mc.yandex.ru/watch/${id}`}
          style={{ position: "absolute", left: "-9999px" }}
          alt=""
        />
      </div>
    </noscript>
  );
}
