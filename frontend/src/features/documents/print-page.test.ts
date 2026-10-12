import { describe, expect, it, vi } from "vitest";

import { PRINT_FRAME_LIFETIME_MS, printPage } from "@/features/documents/print-page";

describe("printPage", () => {
  it("prints the page in a hidden frame and removes it afterwards", () => {
    printPage("<p>Rechnung</p>");
    const frame = document.querySelector("iframe");
    expect(frame).not.toBeNull();
    if (frame === null) return;
    expect(frame.srcdoc).toBe("<p>Rechnung</p>");
    expect(frame.getAttribute("aria-hidden")).toBe("true");
    expect(frame.getAttribute("sandbox")).toBe("allow-same-origin allow-modals");
    expect(frame.tabIndex).toBe(-1);
    const view = frame.contentWindow;
    expect(view).not.toBeNull();
    if (view === null) return;
    const print = vi.spyOn(view, "print").mockImplementation(() => undefined);
    const focus = vi.spyOn(view, "focus");
    frame.dispatchEvent(new Event("load"));
    expect(focus).toHaveBeenCalled();
    expect(print).toHaveBeenCalledOnce();
    view.dispatchEvent(new Event("afterprint"));
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("does nothing when the frame has no window", () => {
    const owner = document.implementation.createHTMLDocument("detached");
    printPage("<p>x</p>", owner);
    const frame = owner.querySelector("iframe");
    expect(frame?.contentWindow ?? null).toBeNull();
    frame?.dispatchEvent(new Event("load"));
    expect(owner.querySelector("iframe")).not.toBeNull();
  });

  it("removes the frame after a while when the browser never reports the end", () => {
    vi.useFakeTimers();
    try {
      printPage("<p>x</p>");
      expect(document.querySelector("iframe")).not.toBeNull();
      vi.advanceTimersByTime(PRINT_FRAME_LIFETIME_MS);
      expect(document.querySelector("iframe")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
