import { describe, expect, it } from "vitest";
import { hasPrivateQueryParams, isPrivateAppPath, shouldNoindexPage } from "./pageRobots";

describe("pageRobots", () => {
  it("marks private app paths", () => {
    expect(isPrivateAppPath("/history")).toBe(true);
    expect(isPrivateAppPath("/thread/abc")).toBe(true);
    expect(isPrivateAppPath("/blog")).toBe(false);
  });

  it("marks tracking query params", () => {
    expect(hasPrivateQueryParams("?WebAppStartParam=foo")).toBe(true);
    expect(hasPrivateQueryParams("?WebAppStartParam=")).toBe(true);
    expect(hasPrivateQueryParams("?WebAppStartParam")).toBe(true);
    expect(hasPrivateQueryParams("?etext=2202.abc")).toBe(true);
    expect(hasPrivateQueryParams("")).toBe(false);
  });

  it("combines homepage with empty WebAppStartParam", () => {
    expect(shouldNoindexPage("/", "?WebAppStartParam=")).toBe(true);
  });

  it("combines path and query checks", () => {
    expect(shouldNoindexPage("/", "?etext=1")).toBe(true);
    expect(shouldNoindexPage("/profile")).toBe(true);
    expect(shouldNoindexPage("/blog", "")).toBe(false);
  });
});
