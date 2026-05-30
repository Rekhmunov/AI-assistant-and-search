import { describe, expect, it } from "vitest";
import { sourcesCountLabel } from "./sourcesCountLabel";

describe("sourcesCountLabel", () => {
  it("pluralizes Russian source count", () => {
    expect(sourcesCountLabel(1)).toEqual({ count: "1", word: "источник" });
    expect(sourcesCountLabel(3)).toEqual({ count: "3", word: "источника" });
    expect(sourcesCountLabel(10)).toEqual({ count: "10", word: "источников" });
    expect(sourcesCountLabel(21)).toEqual({ count: "21", word: "источник" });
  });
});
