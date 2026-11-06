import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  IDEMPOTENCY_HEADER,
  intentOf,
  newKey,
  useIdempotentMutation,
  type Idempotent,
} from "@/features/shared/use-idempotent-mutation";
import { ApiError } from "@/lib/api-error";

function wrapper({ children }: { readonly children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** A request that records its key and answers as told. */
function request(answers: ((key: string) => Promise<string>)[]) {
  const keys: string[] = [];
  const send = vi.fn((_input: string, { headers }: Idempotent) => {
    const key = headers[IDEMPOTENCY_HEADER];
    keys.push(key);
    const answer = answers.shift() ?? (() => Promise.resolve("ok"));
    return answer(key);
  });
  return { keys, send };
}

const lost = () => Promise.reject(new ApiError(0, "network", "offline"));

describe("useIdempotentMutation", () => {
  it("keeps the key of an intent until it succeeds, then starts a new one", async () => {
    const { keys, send } = request([lost, lost]);
    const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), { wrapper });
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await act(() => expect(result.current.mutateAsync("Beispiel AG")).rejects.toThrow());
    }
    await act(() => result.current.mutateAsync("Beispiel AG"));
    await act(() => result.current.mutateAsync("Beispiel AG"));
    const [first, second, third, fourth] = keys;
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    // The answer was lost twice: the same intent is asked again with the same key.
    expect(second).toBe(first);
    expect(third).toBe(first);
    // Done: the same input once more is a new intent.
    expect(fourth).not.toBe(first);
  });

  it("starts a new intent for other input", async () => {
    const { keys, send } = request([lost]);
    const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), { wrapper });
    await act(() => expect(result.current.mutateAsync("Beispiel AG")).rejects.toThrow());
    await act(() => result.current.mutateAsync("Andere AG"));
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("starts a new intent when the server will not run the key's request again", async () => {
    for (const code of ["request_done", "request_unfinished", "idempotency_key_reused"]) {
      const refused = () => Promise.reject(new ApiError(409, code, "refused"));
      const { keys, send } = request([refused]);
      const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), {
        wrapper,
      });
      await act(() => expect(result.current.mutateAsync("Beispiel AG")).rejects.toThrow());
      await act(() => result.current.mutateAsync("Beispiel AG"));
      expect(keys[1]).not.toBe(keys[0]);
    }
  });

  it("keeps the key while the first request still runs", async () => {
    const running = () => Promise.reject(new ApiError(409, "request_in_progress", "wait"));
    const failed = () => Promise.reject(new Error("broken"));
    const { keys, send } = request([running, failed]);
    const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), { wrapper });
    await act(() => expect(result.current.mutateAsync("Beispiel AG")).rejects.toThrow());
    await act(() => expect(result.current.mutateAsync("Beispiel AG")).rejects.toThrow());
    await act(() => result.current.mutateAsync("Beispiel AG"));
    expect(new Set(keys).size).toBe(1);
  });

  it("does not end an intent that another call has replaced meanwhile", async () => {
    let finish: () => void = () => undefined;
    const slow = () =>
      new Promise<string>((resolve) => {
        finish = () => {
          resolve("ok");
        };
      });
    const { keys, send } = request([slow, lost]);
    const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), { wrapper });
    let first: Promise<string> = Promise.resolve("");
    act(() => {
      first = result.current.mutateAsync("Beispiel AG");
    });
    await act(() => expect(result.current.mutateAsync("Andere AG")).rejects.toThrow());
    await act(async () => {
      finish();
      await first;
    });
    await act(() => result.current.mutateAsync("Andere AG"));
    // The late success of the first intent leaves the second one's key alone.
    expect(keys[2]).toBe(keys[1]);
  });
});

describe("intentOf", () => {
  it("tells inputs apart, files by name, size and date", () => {
    const file = (name: string, content: string, lastModified: number) =>
      new File([content], name, { type: "application/pdf", lastModified });
    expect(intentOf(undefined)).toBe("null");
    expect(intentOf({ id: "1" })).toBe(intentOf({ id: "1" }));
    expect(intentOf({ id: "1" })).not.toBe(intentOf({ id: "2" }));
    expect(intentOf([file("a.pdf", "x", 1)])).toBe(intentOf([file("a.pdf", "x", 1)]));
    expect(intentOf([file("a.pdf", "x", 1)])).not.toBe(intentOf([file("b.pdf", "x", 1)]));
    expect(intentOf([file("a.pdf", "x", 1)])).not.toBe(intentOf([file("a.pdf", "xy", 1)]));
    expect(intentOf([file("a.pdf", "x", 1)])).not.toBe(intentOf([file("a.pdf", "x", 2)]));
  });
});

describe("parts of an intent", () => {
  it("give each request of an intent its own key, the same again when it is retried", async () => {
    const seen: string[][] = [];
    let failing = true;
    const send = (_input: string, idempotent: Idempotent) => {
      const keys = [0, 1, 2].map((index) => idempotent.part(index).headers[IDEMPOTENCY_HEADER]);
      seen.push([idempotent.headers[IDEMPOTENCY_HEADER], ...keys]);
      if (failing) {
        failing = false;
        return Promise.reject(new ApiError(0, "network", "offline"));
      }
      return Promise.resolve("ok");
    };
    const { result } = renderHook(() => useIdempotentMutation({ mutationFn: send }), { wrapper });
    await act(() => expect(result.current.mutateAsync("Rechnung.pdf")).rejects.toThrow());
    await act(() => result.current.mutateAsync("Rechnung.pdf"));
    const [first, retried] = seen;
    // The first request's key is part 0; parts differ; a retry asks with the same keys.
    expect(first?.[0]).toBe(first?.[1]);
    expect(new Set(first).size).toBe(3);
    expect(retried).toEqual(first);
  });
});

describe("newKey", () => {
  it("makes random UUIDs of version 4", () => {
    const keys = new Set(Array.from({ length: 50 }, newKey));
    expect(keys.size).toBe(50);
    for (const key of keys) {
      expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    }
  });
});
