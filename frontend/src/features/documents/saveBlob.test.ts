import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveBlob } from "./saveBlob";

const OBJECT_URL = "blob:http://localhost/file-1";
const URL_METHODS = ["createObjectURL", "revokeObjectURL"] as const;

describe("saveBlob", () => {
  // jsdom doesn't implement object URLs, so the test supplies them and puts things back after.
  const originals = URL_METHODS.map(
    (name) => [name, Object.getOwnPropertyDescriptor(URL, name)] as const,
  );
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => OBJECT_URL);
  const revokeObjectURL = vi.fn<(url: string) => void>();

  beforeEach(() => {
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    });
  });

  afterEach(() => {
    for (const [name, descriptor] of originals) {
      if (descriptor) {
        Object.defineProperty(URL, name, descriptor);
      } else {
        Reflect.deleteProperty(URL, name);
      }
    }
  });

  it("clicks a temporary download link and revokes its URL a minute later", () => {
    vi.useFakeTimers();
    let clicked: { href: string; download: string; hidden: boolean } | null = null;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      const link = document.querySelector("a");
      clicked = link && { href: link.href, download: link.download, hidden: link.hidden };
    });
    const blob = new Blob(["hello"], { type: "text/plain" });

    saveBlob(blob, "notes.txt");

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledTimes(1);
    expect(clicked).toEqual({ href: OBJECT_URL, download: "notes.txt", hidden: true });
    expect(document.querySelector("a")).toBeNull();

    vi.advanceTimersByTime(59_999);
    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(revokeObjectURL).toHaveBeenCalledWith(OBJECT_URL);
  });
});
