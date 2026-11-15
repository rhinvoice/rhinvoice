import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

/** Unit queries that several features read; mutations live in features/units. */
export type Unit = components["schemas"]["UnitResponse"];

export const UNITS_KEY = ["units"] as const;

/** The company's units, hidden ones too, in their order (ADR 0046). */
export const unitsQuery = queryOptions({
  queryKey: UNITS_KEY,
  queryFn: () => unwrap(api.GET("/api/units")),
  staleTime: 60_000,
});
