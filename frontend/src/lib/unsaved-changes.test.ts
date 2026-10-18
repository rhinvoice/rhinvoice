import { describe, expect, it, vi } from "vitest";

import { createUnsavedChanges, unsavedChanges } from "@/lib/unsaved-changes";

describe("unsaved changes", () => {
  it("are there while any part of the page holds some", () => {
    const changes = createUnsavedChanges();
    const editor = {};
    const settings = {};
    expect(changes.any()).toBe(false);
    changes.mark(editor, true);
    changes.mark(settings, true);
    changes.mark(editor, false);
    expect(changes.any()).toBe(true);
    changes.mark(settings, false);
    expect(changes.any()).toBe(false);
  });

  it("tell their listeners only when the answer changes", () => {
    const changes = createUnsavedChanges();
    const listener = vi.fn();
    const unsubscribe = changes.subscribe(listener);
    const editor = {};
    changes.mark(editor, false);
    changes.mark(editor, true);
    changes.mark({}, true);
    changes.mark(editor, true);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    changes.mark(editor, false);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("have one record for the page", () => {
    expect(unsavedChanges.any()).toBe(false);
  });
});
