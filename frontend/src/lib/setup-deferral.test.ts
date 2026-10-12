import { afterEach, describe, expect, it } from "vitest";

import { deferSetup, isSetupDeferred, resetSetupDeferral } from "@/lib/setup-deferral";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => {
      data.clear();
    },
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => {
      data.delete(key);
    },
    setItem: (key, value) => {
      data.set(key, value);
    },
  };
}

describe("setup deferral", () => {
  afterEach(() => {
    resetSetupDeferral();
  });

  it("is remembered per browser", () => {
    const storage = memoryStorage();
    expect(isSetupDeferred(storage)).toBe(false);
    deferSetup(storage);
    resetSetupDeferral();
    expect(isSetupDeferred(storage)).toBe(true);
  });

  it("holds for the page without storage", () => {
    expect(isSetupDeferred(null)).toBe(false);
    deferSetup(null);
    expect(isSetupDeferred(null)).toBe(true);
  });
});
