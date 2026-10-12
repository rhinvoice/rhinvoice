import { describe, expect, it } from "vitest";

import { cn } from "@/lib/cn";

describe("cn", () => {
  it("merges conflicting Tailwind classes", () => {
    expect(cn("px-2 py-1", false, undefined, "px-4")).toBe("py-1 px-4");
  });
});
