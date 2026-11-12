import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { TAX_RATES_KEY } from "@/features/shared/tax-rates-api";
import { useIdempotentMutation } from "@/features/shared/use-idempotent-mutation";

export type TaxRateRequest = components["schemas"]["TaxRateRequest"];
export type TaxRatePreset = components["schemas"]["TaxRatePresetResponse"];
export { taxRatesQuery, type RateCategory, type TaxRate } from "@/features/shared/tax-rates-api";

/** The presets of the company's country that no rate comes from yet (e.g. § 24 UStG). */
export const taxRatePresetsQuery = queryOptions({
  queryKey: [...TAX_RATES_KEY, "presets"] as const,
  queryFn: () => unwrap(api.GET("/api/tax-rates/presets")),
});

/** Lines, articles and plans show the rates: they are read anew after a change. */
function useRatesChanged() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: TAX_RATES_KEY });
}

export function useSaveTaxRate(id: string | null) {
  const changed = useRatesChanged();
  return useIdempotentMutation({
    mutationFn: (body: TaxRateRequest, { headers }) =>
      id === null
        ? unwrap(api.POST("/api/tax-rates", { body, headers }))
        : unwrap(api.PUT("/api/tax-rates/{rate_id}", { params: { path: { rate_id: id } }, body })),
    onSuccess: changed,
  });
}

export function useTakeOverPreset() {
  const changed = useRatesChanged();
  return useIdempotentMutation({
    mutationFn: (key: string, { headers }) =>
      unwrap(api.POST("/api/tax-rates/presets/{key}", { params: { path: { key } }, headers })),
    onSuccess: changed,
  });
}

/** Hide a rate (offered no more for new lines) or show it again. */
export function useHideTaxRate() {
  const changed = useRatesChanged();
  return useMutation({
    mutationFn: ({ id, hidden }: { id: string; hidden: boolean }) =>
      unwrap(
        hidden
          ? api.POST("/api/tax-rates/{rate_id}/hide", { params: { path: { rate_id: id } } })
          : api.POST("/api/tax-rates/{rate_id}/show", { params: { path: { rate_id: id } } }),
      ),
    onSuccess: changed,
  });
}

export function useDeleteTaxRate() {
  const changed = useRatesChanged();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/tax-rates/{rate_id}", { params: { path: { rate_id: id } } })),
    onSuccess: changed,
  });
}
