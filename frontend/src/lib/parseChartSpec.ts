export type ChartType = "bar" | "line" | "pie";

export type ChartSeries = {
  name: string;
  values: number[];
};

export type GlosixChartSpec = {
  type: ChartType;
  title?: string;
  labels: string[];
  series: ChartSeries[];
  xLabel?: string;
  yLabel?: string;
};

const MAX_LABELS = 30;
const MAX_SERIES = 5;

const CHART_TYPES = new Set<ChartType>(["bar", "line", "pie"]);

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value.replace(",", ".").trim());
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function readSeries(raw: unknown): ChartSeries[] | null {
  const list = Array.isArray(raw) ? raw : null;
  if (!list || list.length < 1 || list.length > MAX_SERIES) return null;

  const out: ChartSeries[] = [];
  for (const item of list) {
    if (!item || typeof item !== "object") return null;
    const row = item as Record<string, unknown>;
    const name = String(row.name ?? row.label ?? "").trim();
    const valuesRaw = row.values ?? row.data;
    if (!Array.isArray(valuesRaw)) return null;
    const values: number[] = [];
    for (const v of valuesRaw) {
      const n = asNumber(v);
      if (n === null) return null;
      values.push(n);
    }
    if (!values.length) return null;
    out.push({ name: name || "Ряд", values });
  }
  return out;
}

function parseJsonObject(raw: string): unknown {
  const trimmed = raw.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("invalid_json");
    return JSON.parse(match[0]);
  }
}

export function parseChartSpec(raw: string): GlosixChartSpec | null {
  if (!raw.trim()) return null;
  let data: unknown;
  try {
    data = parseJsonObject(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== "object") return null;

  const obj = data as Record<string, unknown>;
  const type = String(obj.type ?? "").trim().toLowerCase() as ChartType;
  if (!CHART_TYPES.has(type)) return null;

  const labelsRaw = obj.labels ?? obj.x;
  if (!Array.isArray(labelsRaw) || labelsRaw.length < 1 || labelsRaw.length > MAX_LABELS) {
    return null;
  }
  const labels = labelsRaw.map((l) => String(l ?? "").trim() || "—");

  const series = readSeries(obj.series ?? obj.datasets);
  if (!series) return null;

  if (type === "pie" && series.length !== 1) return null;

  for (const row of series) {
    if (row.values.length !== labels.length) return null;
  }

  const title = obj.title != null ? String(obj.title).trim() : undefined;
  const xLabel = obj.xLabel != null ? String(obj.xLabel).trim() : undefined;
  const yLabel = obj.yLabel != null ? String(obj.yLabel).trim() : undefined;

  return {
    type,
    title: title || undefined,
    labels,
    series,
    xLabel: xLabel || undefined,
    yLabel: yLabel || undefined,
  };
}

/** Plain-text fallback when copying an answer with a chart block. */
export function formatChartSpecForCopy(spec: GlosixChartSpec): string {
  const lines: string[] = [];
  lines.push(`[График${spec.title ? `: ${spec.title}` : ""}]`);
  lines.push(`Тип: ${spec.type}`);
  if (spec.xLabel) lines.push(`Ось X: ${spec.xLabel}`);
  if (spec.yLabel) lines.push(`Ось Y: ${spec.yLabel}`);
  for (const row of spec.series) {
    const pairs = spec.labels.map((label, i) => `${label}: ${row.values[i]}`);
    lines.push(`${row.name}: ${pairs.join("; ")}`);
  }
  return lines.join("\n");
}
