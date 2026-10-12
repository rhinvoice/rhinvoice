import { fireEvent, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePageShortcut, useSaveShortcut } from "@/components/use-key-shortcuts";
import { SINGLE_KEY_SHORTCUTS_STORAGE_KEY } from "@/lib/shortcuts";

describe("useSaveShortcut", () => {
  it("saves with Ctrl+Enter, also inside inputs", () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("Win32");
    const save = vi.fn();
    const { rerender, unmount } = renderHook(
      ({ enabled }) => {
        useSaveShortcut(save, enabled);
      },
      { initialProps: { enabled: true } },
    );
    const input = document.createElement("input");
    document.body.append(input);
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
    expect(save).toHaveBeenCalledOnce();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(save).toHaveBeenCalledOnce();
    rerender({ enabled: false });
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(save).toHaveBeenCalledOnce();
    unmount();
    input.remove();
  });

  it("uses the latest callback", () => {
    vi.spyOn(navigator, "platform", "get").mockReturnValue("MacIntel");
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ save }) => {
        useSaveShortcut(save);
      },
      { initialProps: { save: first } },
    );
    rerender({ save: second });
    fireEvent.keyDown(window, { key: "Enter", metaKey: true });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });
});

describe("usePageShortcut", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("fires on the plain key outside inputs", () => {
    const handler = vi.fn();
    const { unmount } = renderHook(() => {
      usePageShortcut("c", handler);
    });
    fireEvent.keyDown(window, { key: "c" });
    expect(handler).toHaveBeenCalledOnce();
    const input = document.createElement("input");
    document.body.append(input);
    fireEvent.keyDown(input, { key: "c" });
    expect(handler).toHaveBeenCalledOnce();
    input.remove();
    const handled = new KeyboardEvent("keydown", { key: "c", cancelable: true });
    handled.preventDefault();
    window.dispatchEvent(handled);
    expect(handler).toHaveBeenCalledOnce();
    unmount();
    fireEvent.keyDown(window, { key: "c" });
    expect(handler).toHaveBeenCalledOnce();
  });

  it("is off when single-key shortcuts are disabled", () => {
    localStorage.setItem(SINGLE_KEY_SHORTCUTS_STORAGE_KEY, "off");
    const handler = vi.fn();
    renderHook(() => {
      usePageShortcut("c", handler);
    });
    fireEvent.keyDown(window, { key: "c" });
    expect(handler).not.toHaveBeenCalled();
  });

  it("uses the latest handler", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ handler }) => {
        usePageShortcut("c", handler);
      },
      { initialProps: { handler: first } },
    );
    rerender({ handler: second });
    fireEvent.keyDown(window, { key: "c" });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });
});
