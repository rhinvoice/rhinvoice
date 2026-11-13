import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

/** Tax rate queries that several features read; mutations live in features/tax-rates. */
export type TaxRate = components["schemas"]["TaxRateResponse"];
export type RateCategory = components["schemas"]["RateCategory"];

export const TAX_RATES_KEY = ["tax-rates"] as const;

/** The company's tax rates, hidden ones too, in their order (ADR 0044). */
export const taxRatesQuery = queryOptions({
  queryKey: TAX_RATES_KEY,
  queryFn: () => unwrap(api.GET("/api/tax-rates")),
  staleTime: 60_000,
});
