import { describe, expect, it } from "vitest";
import { extractClipboardImages, normalizePastedImageFile } from "./clipboardImages";

describe("normalizePastedImageFile", () => {
  it("gives pasted blobs a readable filename", () => {
    const file = new File([new Uint8Array([1, 2, 3])], "image.png", { type: "image/png" });
    const normalized = normalizePastedImageFile(file, 0);
    expect(normalized.name).toMatch(/^image-\d+-1\.png$/);
    expect(normalized.type).toBe("image/png");
  });

  it("keeps a real filename from the clipboard", () => {
    const file = new File([new Uint8Array([1])], "screenshot.webp", { type: "image/webp" });
    expect(normalizePastedImageFile(file, 0).name).toBe("screenshot.webp");
  });
});

describe("extractClipboardImages", () => {
  it("returns only image files from clipboard items", () => {
    const dt = new DataTransfer();
    dt.items.add("hello", "text/plain");
    dt.items.add(new File([new Uint8Array([1])], "photo.png", { type: "image/png" }));

    const images = extractClipboardImages(dt);
    expect(images).toHaveLength(1);
    expect(images[0].type).toBe("image/png");
  });
});
