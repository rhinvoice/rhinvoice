import { describe, expect, it } from "vitest";

import { inProgramWindow } from "@/lib/program-window";

describe("inProgramWindow", () => {
  it("knows the program window by the bridge of its web view", () => {
    expect(inProgramWindow({ pywebview: {} })).toBe(true);
    expect(inProgramWindow({})).toBe(false);
  });
});
