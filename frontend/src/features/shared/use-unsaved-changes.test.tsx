import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useHasUnsavedChanges, useUnsavedChanges } from "@/features/shared/use-unsaved-changes";

describe("useUnsavedChanges", () => {
  it("tells the page while a form holds changes, until it is saved or gone", () => {
    const page = renderHook(() => useHasUnsavedChanges());
    const form = renderHook(
      ({ dirty }) => {
        useUnsavedChanges(dirty);
      },
      { initialProps: { dirty: false } },
    );
    expect(page.result.current).toBe(false);
    act(() => {
      form.rerender({ dirty: true });
    });
    expect(page.result.current).toBe(true);
    act(() => {
      form.rerender({ dirty: false });
    });
    expect(page.result.current).toBe(false);
    act(() => {
      form.rerender({ dirty: true });
    });
    act(() => {
      form.unmount();
    });
    expect(page.result.current).toBe(false);
  });
});
