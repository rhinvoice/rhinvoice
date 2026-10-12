import { describe, expect, it } from "vitest";

import { readStorage, writeStorage } from "@/lib/storage";

function throwingStorage(): Storage {
  return {
    length: 0,
    clear: () => undefined,
    key: () => null,
    removeItem: () => undefined,
    getItem: () => {
      throw new Error("denied");
    },
    setItem: () => {
      throw new Error("denied");
    },
  };
}

describe("storage", () => {
  it("reads and writes localStorage", () => {
    writeStorage("rhinvoice.test", "1");
    expect(readStorage("rhinvoice.test")).toBe("1");
    expect(readStorage("rhinvoice.missing")).toBeNull();
  });

  it("survives unavailable storage", () => {
    expect(readStorage("x", throwingStorage())).toBeNull();
    expect(() => {
      writeStorage("x", "1", throwingStorage());
    }).not.toThrow();
    expect(readStorage("x", null)).toBeNull();
    expect(() => {
      writeStorage("x", "1", null);
    }).not.toThrow();
  });
});

describe("blocked storage", () => {
  it("treats a throwing localStorage getter as unavailable", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get: () => {
        throw new Error("SecurityError");
      },
    });
    try {
      expect(readStorage("x")).toBeNull();
      expect(() => {
        writeStorage("x", "1");
      }).not.toThrow();
    } finally {
      if (descriptor !== undefined) Object.defineProperty(globalThis, "localStorage", descriptor);
    }
  });
});
