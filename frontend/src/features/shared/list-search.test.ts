import { describe, expect, it } from "vitest";

import { ariaSort, parseListSearch, toggleSort } from "@/features/shared/list-search";

const SORTS = ["number", "name"] as const;

describe("list search", () => {
  it("parses valid values and falls back for invalid ones", () => {
    expect(
      parseListSearch(
        { q: "abc", archived: true, sort: "name", dir: "desc", page: 3 },
        SORTS,
        "number",
      ),
    ).toEqual({
      q: "abc",
      archived: true,
      sort: "name",
      dir: "desc",
      page: 3,
    });
    expect(
      parseListSearch(
        { q: 5, archived: "yes", sort: "evil", dir: "up", page: -2 },
        SORTS,
        "number",
      ),
    ).toEqual({
      q: "",
      archived: false,
      sort: "number",
      dir: "asc",
      page: 1,
    });
    expect(parseListSearch({ page: 2.5, q: "x".repeat(150) }, SORTS, "name").q).toHaveLength(100);
  });

  it("toggles the sort direction", () => {
    const current = parseListSearch({ sort: "name", page: 4 }, SORTS, "number");
    expect(toggleSort(current, "name")).toEqual({ sort: "name", dir: "desc", page: 1 });
    expect(toggleSort({ ...current, dir: "desc" }, "name")).toEqual({
      sort: "name",
      dir: "asc",
      page: 1,
    });
    expect(toggleSort(current, "number")).toEqual({ sort: "number", dir: "asc", page: 1 });
  });

  it("reports aria-sort", () => {
    const current = parseListSearch({ sort: "name", dir: "desc" }, SORTS, "number");
    expect(ariaSort(current, "name")).toBe("descending");
    expect(ariaSort({ ...current, dir: "asc" }, "name")).toBe("ascending");
    expect(ariaSort(current, "number")).toBe("none");
  });
});
