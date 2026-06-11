import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { captureMaxInitDataFromUrl, waitForMaxWebApp } from "./maxApp";

describe("waitForMaxWebApp", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    delete (window as { WebApp?: unknown }).WebApp;
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (window as { WebApp?: unknown }).WebApp;
  });

  it("resolves when initData appears", async () => {
    const promise = waitForMaxWebApp(500);
    vi.advanceTimersByTime(100);
    window.WebApp = {
      initData: "user=1",
      initDataUnsafe: {},
      platform: "android",
      ready: () => undefined,
    };
    captureMaxInitDataFromUrl();
    vi.advanceTimersByTime(100);
    await promise;
  });

  it("resolves after timeout when bridge is missing", async () => {
    const promise = waitForMaxWebApp(200);
    vi.advanceTimersByTime(250);
    await promise;
  });
});
