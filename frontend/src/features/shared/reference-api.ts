import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

export const countriesQuery = queryOptions({
  queryKey: ["reference", "countries"],
  queryFn: () => unwrap(api.GET("/api/reference/countries")),
  staleTime: Number.POSITIVE_INFINITY,
});

export const unitsQuery = queryOptions({
  queryKey: ["reference", "units"],
  queryFn: () => unwrap(api.GET("/api/reference/units")),
  staleTime: Number.POSITIVE_INFINITY,
});

/** The company countries Rhinvoice supports, with what differs between them. */
export const countryProfilesQuery = queryOptions({
  queryKey: ["reference", "country-profiles"],
  queryFn: () => unwrap(api.GET("/api/reference/country-profiles")),
  // The rates are those of the day.
  staleTime: 24 * 60 * 60_000,
});
