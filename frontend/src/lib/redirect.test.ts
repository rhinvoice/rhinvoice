import { describe, expect, it } from "vitest";

import { safeRedirect } from "@/lib/redirect";

describe("safeRedirect", () => {
  it.each(["/", "/customers", "/settings?tab=security", "/documents/R20260001#lines"])(
    "keeps the in-app path %j",
    (path) => {
      expect(safeRedirect(path)).toBe(path);
    },
  );

  it.each([
    undefined,
    null,
    42,
    "",
    "customers",
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/\\\\evil.example",
    "/\tevil",
    "/a\nb",
    "/x\u0000",
    "/x\u007f",
  ])("rejects %j", (value) => {
    expect(safeRedirect(value)).toBe("/");
  });
});
