import { describe, expect, it, vi } from "vitest";

import { createUndoRegistry } from "@/lib/undo";

describe("undo registry", () => {
  it("runs the current action once", () => {
    const registry = createUndoRegistry();
    const action = vi.fn();
    registry.register(action);
    expect(registry.trigger()).toBe(true);
    expect(registry.trigger()).toBe(false);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("replaces older actions", () => {
    const registry = createUndoRegistry();
    const first = vi.fn();
    const second = vi.fn();
    const withdrawFirst = registry.register(first);
    registry.register(second);
    withdrawFirst(); // must not withdraw the newer action
    expect(registry.trigger()).toBe(true);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("forgets withdrawn actions", () => {
    const registry = createUndoRegistry();
    const action = vi.fn();
    registry.register(action)();
    expect(registry.trigger()).toBe(false);
    expect(action).not.toHaveBeenCalled();
  });
});
