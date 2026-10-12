import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebouncedValue } from "@/components/use-debounced-value";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("updates only after the delay", () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 200), {
      initialProps: { value: "a" },
    });
    expect(result.current).toBe("a");
    rerender({ value: "ab" });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe("a");
    rerender({ value: "abc" });
    act(() => {
      vi.advanceTimersByTime(150);
    });
    expect(result.current).toBe("a");
    act(() => {
      vi.advanceTimersByTime(50);
    });
    expect(result.current).toBe("abc");
  });
});
