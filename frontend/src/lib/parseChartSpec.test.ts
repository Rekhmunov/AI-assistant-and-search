import { describe, expect, it } from "vitest";
import { formatChartSpecForCopy, parseChartSpec } from "./parseChartSpec";

const BAR_JSON = `{
  "type": "bar",
  "title": "Выручка",
  "labels": ["Q1", "Q2"],
  "series": [{"name": "2024", "values": [10, 20]}],
  "yLabel": "млн"
}`;

describe("parseChartSpec", () => {
  it("parses bar chart", () => {
    const spec = parseChartSpec(BAR_JSON);
    expect(spec?.type).toBe("bar");
    expect(spec?.labels).toEqual(["Q1", "Q2"]);
    expect(spec?.series[0].values).toEqual([10, 20]);
  });

  it("accepts datasets alias", () => {
    const spec = parseChartSpec(
      '{"type":"line","labels":["A"],"datasets":[{"label":"X","data":[1]}]}',
    );
    expect(spec?.type).toBe("line");
    expect(spec?.series[0].name).toBe("X");
  });

  it("requires single series for pie", () => {
    expect(
      parseChartSpec(
        '{"type":"pie","labels":["A","B"],"series":[{"name":"S","values":[1,2]},{"name":"T","values":[3,4]}]}',
      ),
    ).toBeNull();
  });

  it("rejects mismatched lengths", () => {
    expect(
      parseChartSpec('{"type":"bar","labels":["A","B"],"series":[{"name":"S","values":[1]}]}'),
    ).toBeNull();
  });

  it("repairs unescaped newlines in json strings", () => {
    const raw = `{
  "type": "bar",
  "title": "T",
  "labels": ["Качество
(процент)"],
  "series": [{"name": "S", "values": [1]}]
}`;
    const spec = parseChartSpec(raw);
    expect(spec?.labels[0]).toContain("Качество");
  });

  it("formats copy text", () => {
    const spec = parseChartSpec(BAR_JSON);
    expect(spec).not.toBeNull();
    const text = formatChartSpecForCopy(spec!);
    expect(text).toContain("[График: Выручка]");
    expect(text).toContain("Q1: 10");
  });
});
