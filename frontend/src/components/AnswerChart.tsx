import { useEffect, useRef } from "react";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Filler,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PieController,
  PointElement,
  Title,
  Tooltip,
  ArcElement,
  type ChartConfiguration,
} from "chart.js";
import { formatChartSpecForCopy, type GlosixChartSpec } from "../lib/parseChartSpec";
import { BlockToolbarActions } from "./BlockToolbarActions";

Chart.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  BarController,
  LineController,
  PieController,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const PALETTE = ["#20808d", "#3b9aa8", "#5eb5c0", "#8ecfd6", "#c2e8ec", "#6b7c93"];

function readAccentColor(): string {
  if (typeof document === "undefined") return PALETTE[0];
  const value = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  return value || PALETTE[0];
}

function palette(count: number): string[] {
  const accent = readAccentColor();
  const colors = [accent, ...PALETTE.filter((c) => c !== accent)];
  return Array.from({ length: count }, (_, i) => colors[i % colors.length]);
}

type Props = {
  spec: GlosixChartSpec;
  partial?: boolean;
};

export function AnswerChart({ spec, partial }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (partial) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    chartRef.current?.destroy();

    const colors = palette(spec.series.length);
    const muted =
      typeof document !== "undefined"
        ? getComputedStyle(document.documentElement).getPropertyValue("--muted").trim() || "#6b7280"
        : "#6b7280";
    const border =
      typeof document !== "undefined"
        ? getComputedStyle(document.documentElement).getPropertyValue("--border").trim() || "#e5e7eb"
        : "#e5e7eb";

    let config: ChartConfiguration;

    if (spec.type === "pie") {
      const row = spec.series[0];
      config = {
        type: "pie",
        data: {
          labels: spec.labels,
          datasets: [
            {
              label: row.name,
              data: row.values,
              backgroundColor: palette(spec.labels.length),
              borderColor: "#fff",
              borderWidth: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: "bottom" },
            title: spec.title ? { display: true, text: spec.title } : { display: false },
          },
        },
      };
    } else {
      config = {
        type: spec.type,
        data: {
          labels: spec.labels,
          datasets: spec.series.map((row, i) => ({
            label: row.name,
            data: row.values,
            borderColor: colors[i],
            backgroundColor: spec.type === "line" ? `${colors[i]}33` : colors[i],
            fill: spec.type === "line",
            tension: 0.25,
          })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              title: spec.xLabel ? { display: true, text: spec.xLabel, color: muted } : { display: false },
              ticks: { color: muted },
              grid: { color: border },
            },
            y: {
              title: spec.yLabel ? { display: true, text: spec.yLabel, color: muted } : { display: false },
              ticks: { color: muted },
              grid: { color: border },
              beginAtZero: true,
            },
          },
          plugins: {
            legend: { position: "bottom", labels: { color: muted } },
            title: spec.title ? { display: true, text: spec.title } : { display: false },
          },
        },
      };
    }

    chartRef.current = new Chart(canvas, config);

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [spec, partial]);

  const copyText = formatChartSpecForCopy(spec);

  return (
    <div className={`answer-chart-block${partial ? " answer-chart-block--partial" : ""}`}>
      <div className="answer-chart-header">
        <span className="answer-chart-label">{spec.title || "График"}</span>
        <BlockToolbarActions
          className="answer-chart-actions"
          copyText={copyText}
          docx={!partial ? { content: copyText, titleHint: spec.title || "График" } : null}
        />
      </div>
      <div className="answer-chart-canvas-wrap" aria-hidden={partial}>
        {partial ? (
          <p className="answer-chart-loading muted-text">Строим график…</p>
        ) : (
          <canvas ref={canvasRef} role="img" aria-label={spec.title || "График"} />
        )}
      </div>
      {!partial && (
        <table className="answer-chart-data-table">
          <thead>
            <tr>
              <th scope="col" />
              {spec.labels.map((label) => (
                <th key={label} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {spec.series.map((row) => (
              <tr key={row.name}>
                <th scope="row">{row.name}</th>
                {row.values.map((value, i) => (
                  <td key={`${row.name}-${i}`}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
