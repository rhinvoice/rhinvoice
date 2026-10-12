/** Search state of list pages, stored in the URL so that it survives navigation. */
export interface ListSearch<S extends string> {
  readonly q: string;
  readonly archived: boolean;
  readonly sort: S;
  readonly dir: "asc" | "desc";
  readonly page: number;
}

export const PAGE_SIZE = 50;

export function parseListSearch<S extends string>(
  raw: Record<string, unknown>,
  sorts: readonly S[],
  defaultSort: S,
): ListSearch<S> {
  const q = typeof raw["q"] === "string" ? raw["q"].slice(0, 100) : "";
  const sort = sorts.find((candidate) => candidate === raw["sort"]) ?? defaultSort;
  const dir = raw["dir"] === "desc" ? "desc" : "asc";
  const pageNumber = Number(raw["page"]);
  const page = Number.isInteger(pageNumber) && pageNumber > 1 ? pageNumber : 1;
  return { q, archived: raw["archived"] === true, sort, dir, page };
}

/** Clicking a header sorts by it; clicking it again flips the direction. */
export function toggleSort<S extends string>(
  current: ListSearch<S>,
  sort: S,
): Pick<ListSearch<S>, "sort" | "dir" | "page"> {
  const dir = current.sort === sort && current.dir === "asc" ? "desc" : "asc";
  return { sort, dir, page: 1 };
}

export function ariaSort<S extends string>(
  current: ListSearch<S>,
  sort: S,
): "ascending" | "descending" | "none" {
  if (current.sort !== sort) return "none";
  return current.dir === "asc" ? "ascending" : "descending";
}
