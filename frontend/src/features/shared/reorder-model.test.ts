import { describe, expect, it } from "vitest";

import { moved, moveTarget } from "@/features/shared/reorder-model";

describe("reordering", () => {
  it("moves with Alt+↑/↓ within the list", () => {
    expect(moveTarget({ altKey: true, key: "ArrowUp" }, 1, 3)).toBe(0);
    expect(moveTarget({ altKey: true, key: "ArrowDown" }, 1, 3)).toBe(2);
    expect(moveTarget({ altKey: true, key: "ArrowUp" }, 0, 3)).toBeNull();
    expect(moveTarget({ altKey: true, key: "ArrowDown" }, 2, 3)).toBeNull();
    expect(moveTarget({ altKey: false, key: "ArrowUp" }, 1, 3)).toBeNull();
    expect(moveTarget({ altKey: true, key: "Enter" }, 1, 3)).toBeNull();
  });

  it("moves an id to another place", () => {
    expect(moved(["a", "b", "c"], 0, 2)).toEqual(["b", "c", "a"]);
    expect(moved(["a", "b", "c"], 2, 0)).toEqual(["c", "a", "b"]);
    expect(moved(["a", "b", "c"], 1, 1)).toEqual(["a", "b", "c"]);
    expect(moved(["a"], 3, 0)).toEqual(["a"]);
  });
});
