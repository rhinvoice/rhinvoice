import { renderHook, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchFile, saveFile, type DownloadedFile } from "@/features/shared/file-download";
import { useSaveFile } from "@/features/shared/use-save-file";
import { ApiError } from "@/lib/api-error";

vi.mock("@/features/shared/file-download", () => ({ fetchFile: vi.fn(), saveFile: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

describe("useSaveFile", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("saves the loaded file", async () => {
    const file: DownloadedFile = { blob: new Blob(["%PDF"]), name: "R1.pdf" };
    vi.mocked(fetchFile).mockResolvedValue(file);
    const { result } = renderHook(() => useSaveFile());
    result.current("/api/reminders/1/pdf");
    await waitFor(() => {
      expect(saveFile).toHaveBeenCalledWith(file);
    });
    expect(fetchFile).toHaveBeenCalledWith("/api/reminders/1/pdf", "document.pdf");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("shows why a file could not be loaded", async () => {
    vi.mocked(fetchFile).mockRejectedValue(new ApiError(0, "network", "HTTP 0"));
    const { result } = renderHook(() => useSaveFile());
    result.current("/api/reminders/1/pdf");
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "Keine Verbindung zum Server. Bitte prüfen Sie Ihre Verbindung.",
        { duration: Infinity },
      );
    });
    expect(saveFile).not.toHaveBeenCalled();
  });

  it("falls back to a general message", async () => {
    vi.mocked(fetchFile).mockRejectedValue(null);
    const { result } = renderHook(() => useSaveFile());
    result.current("/api/reminders/1/pdf");
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledOnce();
    });
    expect(vi.mocked(toast.error).mock.calls[0]?.[0]).not.toBe("");
  });
});
