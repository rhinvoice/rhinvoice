import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "@/lib/api-error";

describe("toApiError", () => {
  it("reads the API error format", () => {
    const error = toApiError(422, {
      error: { code: "validation_error", message: "invalid", details: { email: "bad", n: 1 } },
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(422);
    expect(error.code).toBe("validation_error");
    expect(error.message).toBe("invalid");
    expect(error.details).toEqual({ email: "bad" });
    expect(error.isUnauthorized).toBe(false);
  });

  it("falls back to the code as message and empty details", () => {
    const error = toApiError(401, { error: { code: "authentication_failed", details: [] } });
    expect(error.message).toBe("authentication_failed");
    expect(error.details).toEqual({});
    expect(error.isUnauthorized).toBe(true);
  });

  it.each([
    [500, "boom", "http_error", "HTTP 500"],
    [502, { error: "x" }, "http_error", "HTTP 502"],
    [500, { error: { code: 5 } }, "http_error", "HTTP 500"],
    [500, [], "http_error", "HTTP 500"],
    [0, undefined, "network", "HTTP 0"],
  ])("handles unexpected body %#", (status, body, code, message) => {
    const error = toApiError(status, body);
    expect(error.code).toBe(code);
    expect(error.message).toBe(message);
  });

  it("defaults details to an empty object", () => {
    expect(new ApiError(400, "x", "y").details).toEqual({});
  });
});
