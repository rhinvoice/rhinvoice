import { fireEvent, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  GO_PREFIX_TIMEOUT_MS,
  handleShortcut,
  useGlobalShortcuts,
  type GlobalShortcutHandlers,
} from "@/app/shell/use-global-shortcuts";
import type { KeyEventLike } from "@/lib/shortcuts";

function handlers(): GlobalShortcutHandlers & Record<string, ReturnType<typeof vi.fn>> {
  return {
    openPalette: vi.fn(),
    openHelp: vi.fn(),
    newInvoice: vi.fn(),
    newQuote: vi.fn(),
    undo: vi.fn(() => true),
    focusSearch: vi.fn(),
    goTo: vi.fn((key: string) => key === "c"),
  };
}

function key(value: string, overrides: Partial<KeyEventLike> = {}): KeyEventLike {
  return {
    key: value,
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    target: document.body,
    ...overrides,
  };
}

describe("handleShortcut", () => {
  it("opens the palette with the platform modifier, even in inputs", () => {
    const h = handlers();
    const input = document.createElement("input");
    expect(handleShortcut(key("k", { metaKey: true, target: input }), h, "MacIntel", true)).toEqual(
      {
        handled: true,
        goPending: false,
      },
    );
    expect(h.openPalette).toHaveBeenCalledOnce();
  });

  it("undoes with the platform modifier and Z, but not in inputs", () => {
    const h = handlers();
    expect(handleShortcut(key("z", { metaKey: true }), h, "MacIntel", false)).toEqual({
      handled: true,
      goPending: false,
    });
    expect(h.undo).toHaveBeenCalledOnce();
    vi.mocked(h.undo).mockReturnValueOnce(false);
    expect(handleShortcut(key("z", { ctrlKey: true }), h, "Win32", true).handled).toBe(false);
    expect(h.undo).toHaveBeenCalledTimes(2);
    const input = document.createElement("input");
    expect(
      handleShortcut(key("z", { ctrlKey: true, target: input }), h, "Win32", false).handled,
    ).toBe(false);
    expect(
      handleShortcut(key("Z", { ctrlKey: true, shiftKey: true }), h, "Win32", false).handled,
    ).toBe(false);
    expect(h.undo).toHaveBeenCalledTimes(2);
  });

  it("handles single key shortcuts", () => {
    const h = handlers();
    expect(handleShortcut(key("?"), h, "Win32", false).handled).toBe(true);
    expect(handleShortcut(key("n"), h, "Win32", false).handled).toBe(true);
    expect(handleShortcut(key("/"), h, "Win32", false).handled).toBe(true);
    expect(handleShortcut(key("q"), h, "Win32", false).handled).toBe(true);
    expect(h.newQuote).toHaveBeenCalledOnce();
    expect(h.openHelp).toHaveBeenCalledOnce();
    expect(h.newInvoice).toHaveBeenCalledOnce();
    expect(h.focusSearch).toHaveBeenCalledOnce();
    expect(handleShortcut(key("x"), h, "Win32", false)).toEqual({
      handled: false,
      goPending: false,
    });
  });

  it("supports the two key go-to sequence", () => {
    const h = handlers();
    expect(handleShortcut(key("g"), h, "Win32", false)).toEqual({ handled: true, goPending: true });
    expect(handleShortcut(key("C"), h, "Win32", true)).toEqual({ handled: true, goPending: false });
    expect(h.goTo).toHaveBeenCalledWith("c");
    expect(handleShortcut(key("z"), h, "Win32", true)).toEqual({
      handled: false,
      goPending: false,
    });
  });

  it("ignores single keys while typing", () => {
    const h = handlers();
    const input = document.createElement("input");
    expect(handleShortcut(key("n", { target: input }), h, "Win32", false).handled).toBe(false);
    expect(handleShortcut(key("c", { target: input }), h, "Win32", true).handled).toBe(false);
    expect(h.newInvoice).not.toHaveBeenCalled();
  });
});

describe("single key shortcuts can be turned off (WCAG 2.1.4)", () => {
  it("keeps only the palette shortcut", () => {
    const h = handlers();
    expect(handleShortcut(key("n"), h, "Win32", false, false)).toEqual({
      handled: false,
      goPending: false,
    });
    expect(handleShortcut(key("c"), h, "Win32", true, false).handled).toBe(false);
    expect(handleShortcut(key("k", { ctrlKey: true }), h, "Win32", false, false).handled).toBe(
      true,
    );
    expect(h.newInvoice).not.toHaveBeenCalled();
    expect(h.goTo).not.toHaveBeenCalled();
  });

  it("is passed through by the hook", () => {
    const h = handlers();
    renderHook(() => {
      useGlobalShortcuts(h, { singleKeys: false });
    });
    fireEvent.keyDown(window, { key: "n" });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true, metaKey: true });
    expect(h.newInvoice).not.toHaveBeenCalled();
    expect(h.openPalette).toHaveBeenCalledOnce();
  });
});

describe("useGlobalShortcuts", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("listens to keydown events and prevents the default action", () => {
    const h = handlers();
    const { unmount } = renderHook(() => {
      useGlobalShortcuts(h);
    });
    const event = new KeyboardEvent("keydown", { key: "n", cancelable: true });
    window.dispatchEvent(event);
    expect(h.newInvoice).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);

    const unhandled = new KeyboardEvent("keydown", { key: "x", cancelable: true });
    window.dispatchEvent(unhandled);
    expect(unhandled.defaultPrevented).toBe(false);
    unmount();
    fireEvent.keyDown(window, { key: "n" });
    expect(h.newInvoice).toHaveBeenCalledOnce();
  });

  it("expires the go prefix after a timeout", () => {
    const h = handlers();
    renderHook(() => {
      useGlobalShortcuts(h);
    });
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "c" });
    expect(h.goTo).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(window, { key: "g" });
    vi.advanceTimersByTime(GO_PREFIX_TIMEOUT_MS);
    fireEvent.keyDown(window, { key: "c" });
    expect(h.goTo).toHaveBeenCalledTimes(1);
  });

  it("skips events that were already handled and can be disabled", () => {
    const h = handlers();
    const { rerender } = renderHook(
      ({ enabled }) => {
        useGlobalShortcuts(h, { enabled });
      },
      { initialProps: { enabled: true } },
    );
    const handled = new KeyboardEvent("keydown", { key: "n", cancelable: true });
    handled.preventDefault();
    window.dispatchEvent(handled);
    expect(h.newInvoice).not.toHaveBeenCalled();
    rerender({ enabled: false });
    fireEvent.keyDown(window, { key: "n" });
    expect(h.newInvoice).not.toHaveBeenCalled();
  });

  it("always calls the latest handlers", () => {
    const first = handlers();
    const second = handlers();
    const { rerender } = renderHook(
      ({ current }) => {
        useGlobalShortcuts(current);
      },
      { initialProps: { current: first } },
    );
    rerender({ current: second });
    fireEvent.keyDown(window, { key: "?" });
    expect(first.openHelp).not.toHaveBeenCalled();
    expect(second.openHelp).toHaveBeenCalledOnce();
  });
});
