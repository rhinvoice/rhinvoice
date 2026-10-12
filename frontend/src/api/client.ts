import createClient from "openapi-fetch";

import type { paths } from "@/api/schema";
import { toApiError } from "@/lib/api-error";

/** Required on every state changing request (CSRF protection, see ADR 0003). */
export const CLIENT_HEADER = "X-Rhinvoice-Client";

export const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
  headers: { [CLIENT_HEADER]: "web" },
});

interface FetchResult<T> {
  readonly data?: T;
  readonly error?: unknown;
  readonly response: Response;
}

/**
 * Await an openapi-fetch call and return its data or throw an ApiError.
 * Network failures become an ApiError with status 0 and code "network".
 */
export async function unwrap<T>(request: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await request;
  } catch {
    throw toApiError(0, undefined);
  }
  if (!result.response.ok) {
    throw toApiError(result.response.status, result.error);
  }
  return result.data as T;
}

export type { components, paths } from "@/api/schema";
