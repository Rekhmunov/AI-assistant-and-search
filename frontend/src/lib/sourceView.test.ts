import { describe, expect, it } from "vitest";
import { parseSourceViewUrl } from "./sourceView";

describe("parseSourceViewUrl", () => {
  it("accepts https URLs", () => {
    expect(parseSourceViewUrl("https://example.com/a")).toBe("https://example.com/a");
  });

  it("rejects non-http schemes", () => {
    expect(parseSourceViewUrl("javascript:alert(1)")).toBeNull();
  });

  it("rejects invalid URLs", () => {
    expect(parseSourceViewUrl("not-a-url")).toBeNull();
  });
});
