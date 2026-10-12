import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useSingleKeyShortcuts } from "@/components/use-single-key-shortcuts";
import { SINGLE_KEY_SHORTCUTS_STORAGE_KEY } from "@/lib/shortcuts";

describe("useSingleKeyShortcuts", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("is enabled by default and can be turned off and on", () => {
    const { result } = renderHook(() => useSingleKeyShortcuts());
    expect(result.current[0]).toBe(true);
    act(() => {
      result.current[1](false);
    });
    expect(result.current[0]).toBe(false);
    expect(localStorage.getItem(SINGLE_KEY_SHORTCUTS_STORAGE_KEY)).toBe("off");
    act(() => {
      result.current[1](true);
    });
    expect(result.current[0]).toBe(true);
  });

  it("follows changes made in other tabs", () => {
    const { result, unmount } = renderHook(() => useSingleKeyShortcuts());
    act(() => {
      localStorage.setItem(SINGLE_KEY_SHORTCUTS_STORAGE_KEY, "off");
      window.dispatchEvent(new StorageEvent("storage"));
    });
    expect(result.current[0]).toBe(false);
    unmount();
  });
});
