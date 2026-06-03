import { describe, expect, it } from "vitest";
import { isDocxExportableBlock } from "./isDocxExportableBlock";

describe("isDocxExportableBlock", () => {
  it("allows txt blocks with legal text", () => {
    const text = "ПУБЛИЧНАЯ ОФЕРТА\n".repeat(10);
    expect(isDocxExportableBlock(text, "txt")).toBe(true);
  });

  it("rejects partial stream", () => {
    expect(isDocxExportableBlock("x".repeat(100), "txt", true)).toBe(false);
  });

  it("rejects javascript", () => {
    expect(isDocxExportableBlock("console.log(1)".repeat(20), "javascript")).toBe(false);
  });
});
