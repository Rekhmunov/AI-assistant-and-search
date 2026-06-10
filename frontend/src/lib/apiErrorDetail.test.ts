import { describe, expect, it } from "vitest";
import { formatApiErrorDetail } from "./apiErrorDetail";

describe("formatApiErrorDetail", () => {
  it("accepts plain string detail", () => {
    expect(formatApiErrorDetail("Сервис временно недоступен", "fallback")).toBe(
      "Сервис временно недоступен",
    );
  });

  it("formats FastAPI validation array", () => {
    const body = {
      detail: [
        {
          type: "string_too_long",
          loc: ["body", "query"],
          msg: "String should have at most 2000 characters",
        },
      ],
    };
    expect(formatApiErrorDetail(body, "fallback")).toContain("2000");
  });
});
