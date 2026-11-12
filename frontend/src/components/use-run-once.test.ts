import { act, renderHook } from "@testing-library/react";
import type { SyntheticEvent } from "react";
import { describe, expect, it, vi } from "vitest";

import { useRunOnce, useSubmitOnce } from "@/components/use-run-once";

function deferred() {
  let settle: (fail: boolean) => void = () => undefined;
  const promise = new Promise<string>((resolve, reject) => {
    settle = (fail) => {
      if (fail) reject(new Error("refused"));
      else resolve("done");
    };
  });
  return { promise, settle };
}

describe("useRunOnce", () => {
  it("ignores further runs until the first has settled", async () => {
    const { result } = renderHook(() => useRunOnce());
    const first = deferred();
    let calls = 0;
    const action = () => {
      calls += 1;
      return first.promise;
    };
    let running: Promise<string | undefined> = Promise.resolve(undefined);
    let second: Promise<string | undefined> = Promise.resolve(undefined);
    act(() => {
      // Both in one tick, before React renders again: the second must not start.
      running = result.current.run(action);
      second = result.current.run(action);
    });
    expect(calls).toBe(1);
    expect(result.current.busy).toBe(true);
    await expect(second).resolves.toBeUndefined();
    await act(async () => {
      first.settle(false);
      await running;
    });
    await expect(running).resolves.toBe("done");
    expect(result.current.busy).toBe(false);
    await expect(act(() => result.current.run(() => Promise.resolve("again")))).resolves.toBe(
      "again",
    );
  });

  it("unlocks when the action fails", async () => {
    const { result } = renderHook(() => useRunOnce());
    const failing = deferred();
    let running: Promise<string | undefined> = Promise.resolve(undefined);
    act(() => {
      running = result.current.run(() => failing.promise);
    });
    await act(async () => {
      failing.settle(true);
      await running.catch(() => undefined);
    });
    await expect(running).rejects.toThrow("refused");
    expect(result.current.busy).toBe(false);
    await expect(result.current.run(() => Promise.resolve("next"))).resolves.toBe("next");
  });
});

describe("useRunOnce finish", () => {
  it("runs nothing more once finished", async () => {
    const { result } = renderHook(() => useRunOnce());
    act(() => {
      result.current.finish();
    });
    expect(result.current.busy).toBe(true);
    await expect(result.current.run(() => Promise.resolve("late"))).resolves.toBeUndefined();
  });
});

describe("useSubmitOnce", () => {
  it("submits once at a time and keeps the page from reloading", async () => {
    let settle: () => void = () => undefined;
    const handler = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          settle = resolve;
        }),
    );
    const { result } = renderHook(() => useSubmitOnce(handler));
    const preventDefault = vi.fn();
    act(() => {
      result.current.submit({ preventDefault } as unknown as SyntheticEvent);
      result.current.submit();
    });
    expect(handler).toHaveBeenCalledOnce();
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(result.current.busy).toBe(true);
    await act(async () => {
      settle();
      await Promise.resolve();
    });
    expect(result.current.busy).toBe(false);
  });
});
