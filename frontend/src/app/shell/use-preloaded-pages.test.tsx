import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PRELOAD_DELAY_MS,
  inProgramWindow,
  usePreloadedPages,
} from "@/app/shell/use-preloaded-pages";

const loadRouteChunk = vi.fn<(route: string) => Promise<void> | undefined>();
const router = {
  routesById: { root: "root", invoices: "invoices", broken: "broken" },
  loadRouteChunk,
};

vi.mock("@tanstack/react-router", () => ({ useRouter: () => router }));

describe("usePreloadedPages", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("pywebview", {});
    loadRouteChunk.mockImplementation((route) =>
      route === "broken" ? Promise.reject(new Error("offline")) : undefined,
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("loads every page shortly after the start", async () => {
    renderHook(() => {
      usePreloadedPages();
    });
    expect(loadRouteChunk).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(PRELOAD_DELAY_MS);
    // A page that fails here is loaded on its visit; nothing is left unhandled.
    expect(loadRouteChunk.mock.calls).toEqual([["root"], ["invoices"], ["broken"]]);
  });

  it("leaves a browser loading each page on its visit", () => {
    vi.unstubAllGlobals();
    renderHook(() => {
      usePreloadedPages();
    });
    vi.advanceTimersByTime(PRELOAD_DELAY_MS);
    expect(loadRouteChunk).not.toHaveBeenCalled();
  });

  it("loads nothing when the shell is gone before", () => {
    const { unmount } = renderHook(() => {
      usePreloadedPages();
    });
    unmount();
    vi.advanceTimersByTime(PRELOAD_DELAY_MS);
    expect(loadRouteChunk).not.toHaveBeenCalled();
  });
});

describe("inProgramWindow", () => {
  it("knows the program window by the bridge of its web view", () => {
    expect(inProgramWindow({ pywebview: {} })).toBe(true);
    expect(inProgramWindow({})).toBe(false);
  });
});
