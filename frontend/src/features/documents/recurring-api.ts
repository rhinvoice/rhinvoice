import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Plan = components["schemas"]["PlanResponse"];
export type PlanRequest = components["schemas"]["PlanRequest"];
export type PlanRun = Plan["runs"][number];
export type Interval = Plan["interval"];
export type PlanAction = Plan["action"];

const PLANS_KEY = ["recurring"] as const;

export const plansQuery = queryOptions({
  queryKey: PLANS_KEY,
  queryFn: () => unwrap(api.GET("/api/recurring")),
});

export function planQuery(planId: string) {
  return queryOptions({
    queryKey: [...PLANS_KEY, planId] as const,
    queryFn: () =>
      unwrap(api.GET("/api/recurring/{plan_id}", { params: { path: { plan_id: planId } } })),
  });
}

export function useSavePlan(planId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanRequest) =>
      planId === null
        ? unwrap(api.POST("/api/recurring", { body }))
        : unwrap(
            api.PUT("/api/recurring/{plan_id}", { params: { path: { plan_id: planId } }, body }),
          ),
    onSuccess: (plan) => {
      client.setQueryData(planQuery(plan.id).queryKey, plan);
      void client.invalidateQueries({ queryKey: PLANS_KEY, exact: true });
    },
  });
}

export function usePlanAction(action: "pause" | "resume") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) =>
      action === "pause"
        ? unwrap(
            api.POST("/api/recurring/{plan_id}/pause", { params: { path: { plan_id: planId } } }),
          )
        : unwrap(
            api.POST("/api/recurring/{plan_id}/resume", { params: { path: { plan_id: planId } } }),
          ),
    onSuccess: (plan) => {
      client.setQueryData(planQuery(plan.id).queryKey, plan);
      void client.invalidateQueries({ queryKey: PLANS_KEY, exact: true });
    },
  });
}

export function useDeletePlan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) =>
      unwrap(api.DELETE("/api/recurring/{plan_id}", { params: { path: { plan_id: planId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}
