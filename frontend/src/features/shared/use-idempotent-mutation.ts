import {
  useMutation,
  type UseMutationOptions,
  type UseMutationResult,
} from "@tanstack/react-query";
import { useRef } from "react";

import { ApiError } from "@/lib/api-error";

/** Sent with each request that creates or sends something (ADR 0041). */
export const IDEMPOTENCY_HEADER = "Idempotency-Key";

/** The header to send along: openapi-fetch takes it as an option, fetch as headers. */
export interface IdempotencyHeaders {
  readonly headers: Readonly<Record<typeof IDEMPOTENCY_HEADER, string>>;
}

/** The keys of one intent: its request, or each of several (e.g. one per uploaded file). */
export interface Idempotent extends IdempotencyHeaders {
  readonly part: (index: number) => IdempotencyHeaders;
}

/**
 * Answers after which the key will not run its request again (it went through, its outcome is
 * unclear, or it belongs to another request): the next attempt is a new intent with a new key.
 */
const SPENT = new Set(["request_done", "request_unfinished", "idempotency_key_reused"]);

interface Intent {
  readonly input: string;
  readonly keys: string[];
}

/**
 * A mutation whose requests carry an Idempotency-Key (ADR 0041). One key belongs to one
 * intent: the same input sent again, e.g. after its answer was lost, keeps the key, and the
 * server answers from the first request instead of creating, paying or sending twice. A success
 * ends the intent, and so does other input: they get a new key.
 */
export function useIdempotentMutation<TData, TVariables = void, TContext = unknown>({
  mutationFn,
  ...options
}: Omit<UseMutationOptions<TData, Error, TVariables, TContext>, "mutationFn"> & {
  readonly mutationFn: (variables: TVariables, idempotent: Idempotent) => Promise<TData>;
}): UseMutationResult<TData, Error, TVariables, TContext> {
  const intent = useRef<Intent | null>(null);
  return useMutation({
    ...options,
    mutationFn: async (variables) => {
      const input = intentOf(variables);
      if (intent.current?.input !== input) intent.current = { input, keys: [] };
      const current = intent.current;
      const part = (index: number): IdempotencyHeaders => {
        current.keys[index] ??= newKey();
        return { headers: { [IDEMPOTENCY_HEADER]: current.keys[index] } };
      };
      const end = () => {
        if (intent.current === current) intent.current = null;
      };
      try {
        const data = await mutationFn(variables, { ...part(0), part });
        end();
        return data;
      } catch (caught) {
        if (caught instanceof ApiError && SPENT.has(caught.code)) end();
        throw caught;
      }
    },
  });
}

/** What makes two calls the same intent: their input, files by name, size and date. */
export function intentOf(variables: unknown): string {
  return JSON.stringify(variables ?? null, (_name, value: unknown) =>
    value instanceof File
      ? `file:${value.name}:${String(value.size)}:${String(value.lastModified)}`
      : value,
  );
}

/**
 * A random UUID (version 4). Not crypto.randomUUID(): browsers offer it only on HTTPS and
 * localhost, and Rhinvoice may be reached by plain HTTP within a network.
 */
export function newKey(): string {
  // Version 4 (byte 6) and the RFC 4122 variant (byte 8) over random bits.
  const bytes = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte, index) =>
    index === 6 ? (byte & 0x0f) | 0x40 : index === 8 ? (byte & 0x3f) | 0x80 : byte,
  );
  const hex = bytes.map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
