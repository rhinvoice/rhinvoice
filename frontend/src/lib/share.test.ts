import { afterEach, describe, expect, it, vi } from "vitest";

import { canSharePdf, pdfFile, shareFile, type ShareTarget } from "@/lib/share";

describe("share", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("makes a PDF file", () => {
    const file = pdfFile(new Blob(["%PDF-"]), "R20260001.pdf");
    expect(file.name).toBe("R20260001.pdf");
    expect(file.type).toBe("application/pdf");
  });

  it("asks the browser whether it can share PDF files", () => {
    const canShare = vi.fn((data?: ShareData) => data?.files?.[0]?.type === "application/pdf");
    const share = vi.fn(() => Promise.resolve());
    expect(canSharePdf({ canShare, share })).toBe(true);
    expect(canSharePdf({ canShare: () => false, share })).toBe(false);
    expect(canSharePdf({ share })).toBe(false);
    expect(canSharePdf({ canShare })).toBe(false);
    expect(canSharePdf(undefined)).toBe(false);
    const throwing: ShareTarget = {
      canShare: () => {
        throw new TypeError("no files");
      },
      share,
    };
    expect(canSharePdf(throwing)).toBe(false);
  });

  it("takes the navigator by default", () => {
    // jsdom has no Web Share API.
    expect(canSharePdf()).toBe(false);
    vi.stubGlobal("navigator", { canShare: () => true, share: () => Promise.resolve() });
    expect(canSharePdf()).toBe(true);
    vi.stubGlobal("navigator", undefined);
    expect(canSharePdf()).toBe(false);
  });

  it("shares the file, and a closed sheet is no error", async () => {
    const file = pdfFile(new Blob(["%PDF-"]), "R20260001.pdf");
    const share = vi.fn(() => Promise.resolve());
    await expect(shareFile(file, "Rechnung R20260001", { share })).resolves.toBe("shared");
    expect(share).toHaveBeenCalledWith({ files: [file], title: "Rechnung R20260001" });
    const aborted = () => Promise.reject(new DOMException("closed", "AbortError"));
    await expect(shareFile(file, "x", { share: aborted })).resolves.toBe("cancelled");
    const denied = () => Promise.reject(new DOMException("no", "NotAllowedError"));
    await expect(shareFile(file, "x", { share: denied })).rejects.toThrow("no");
    await expect(shareFile(file, "x", {})).rejects.toThrow("sharing is not supported");
    vi.stubGlobal("navigator", { share });
    await expect(shareFile(file, "y")).resolves.toBe("shared");
  });
});
