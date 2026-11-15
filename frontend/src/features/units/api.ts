import { queryOptions, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { UNITS_KEY } from "@/features/shared/units-api";
import { useIdempotentMutation } from "@/features/shared/use-idempotent-mutation";

export type UnitRequest = components["schemas"]["UnitRequest"];
export type UnitOffer = components["schemas"]["UnitOfferResponse"];
export type UnitGroup = components["schemas"]["UnitGroup"];
export type UnitCode = components["schemas"]["UnitCodeResponse"];
export type Removal = components["schemas"]["Removal"];
export { unitsQuery, type Unit } from "@/features/shared/units-api";

/** The catalogue entries not taken yet, then the hidden units (ADR 0046). */
export const unitPresetsQuery = queryOptions({
  queryKey: [...UNITS_KEY, "presets"] as const,
  queryFn: () => unwrap(api.GET("/api/units/presets")),
});

/** The EN 16931 unit code list; it changes with a release only. */
export const unitCodesQuery = queryOptions({
  queryKey: [...UNITS_KEY, "codes"] as const,
  queryFn: () => unwrap(api.GET("/api/units/codes")),
  staleTime: Number.POSITIVE_INFINITY,
});

/** Lines, articles and plans show the units: they are read anew after a change. */
function useUnitsChanged() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: UNITS_KEY });
}

export function useSaveUnit(id: string | null) {
  const changed = useUnitsChanged();
  return useIdempotentMutation({
    mutationFn: (body: UnitRequest, { headers }) =>
      id === null
        ? unwrap(api.POST("/api/units", { body, headers }))
        : unwrap(
            api.PUT("/api/units/{unit_id}", { params: { path: { unit_id: id } }, body, headers }),
          ),
    onSuccess: changed,
  });
}

/** Delete a unit nothing uses, else hide it; the answer says which. */
export function useRemoveUnit() {
  const changed = useUnitsChanged();
  return useIdempotentMutation({
    mutationFn: (id: string, { headers }) =>
      unwrap(
        api.POST("/api/units/{unit_id}/remove", { params: { path: { unit_id: id } }, headers }),
      ),
    onSuccess: changed,
  });
}

/** Put the units offered in a new order (every one of them, each once). */
export function useOrderUnits() {
  const changed = useUnitsChanged();
  return useIdempotentMutation({
    mutationFn: (unitIds: readonly string[], { headers }) =>
      unwrap(api.PUT("/api/units/order", { body: { unit_ids: [...unitIds] }, headers })),
    onSuccess: changed,
  });
}

/** Add catalogue entries and show hidden units again, at the end of the list. */
export function useTakeOverUnits() {
  const changed = useUnitsChanged();
  return useIdempotentMutation({
    mutationFn: (
      chosen: { readonly keys: readonly string[]; readonly unitIds: readonly string[] },
      { headers },
    ) =>
      unwrap(
        api.POST("/api/units/presets", {
          body: { keys: [...chosen.keys], unit_ids: [...chosen.unitIds] },
          headers,
        }),
      ),
    onSuccess: changed,
  });
}
