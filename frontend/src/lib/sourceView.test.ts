import { describe, expect, it } from "vitest";
import { detectIframeEmbedState, normalizeLinkHref, parseSourceViewUrl } from "./sourceView";

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

describe("normalizeLinkHref", () => {
  it("adds https to domain paths", () => {
    expect(normalizeLinkHref("max.ru/mfcryazan_bot")).toBe("https://max.ru/mfcryazan_bot");
  });
});

describe("detectIframeEmbedState", () => {
  it("treats cross-origin iframe as ready", () => {
    const iframe = {
      contentDocument: null,
      contentWindow: {
        get document() {
          throw new DOMException("Blocked", "SecurityError");
        },
      },
    } as unknown as HTMLIFrameElement;

    expect(detectIframeEmbedState(iframe)).toBe("ready");
  });

  it("treats empty about:blank iframe as blocked", () => {
    const iframe = {
      contentDocument: {
        body: { innerHTML: "", innerText: "" },
        defaultView: { location: { href: "about:blank" } },
      },
      contentWindow: null,
    } as unknown as HTMLIFrameElement;

    expect(detectIframeEmbedState(iframe)).toBe("blocked");
  });

  it("treats iframe with visible text as ready", () => {
    const iframe = {
      contentDocument: {
        body: { innerHTML: "<p>Hello</p>", innerText: "Hello" },
        defaultView: { location: { href: "https://example.com/" } },
      },
      contentWindow: null,
    } as unknown as HTMLIFrameElement;

    expect(detectIframeEmbedState(iframe)).toBe("ready");
  });
});
