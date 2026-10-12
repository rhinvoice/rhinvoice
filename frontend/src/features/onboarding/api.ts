import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Onboarding = components["schemas"]["OnboardingResponse"];
export type OnboardingStep = Onboarding["steps"][number]["key"];

const ONBOARDING_KEY = ["onboarding"];

export const onboardingQuery = queryOptions({
  queryKey: ONBOARDING_KEY,
  queryFn: () => unwrap(api.GET("/api/onboarding")),
  // The steps follow from data saved on other pages: ask again on every visit.
  staleTime: 0,
});

export function useCheckNumbering() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/onboarding/numbering-checked")),
    onSuccess: (onboarding) => {
      client.setQueryData(ONBOARDING_KEY, onboarding);
    },
  });
}

export function useShowOnboarding() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/onboarding/show")),
    onSuccess: (onboarding) => {
      client.setQueryData(ONBOARDING_KEY, onboarding);
    },
  });
}

export function useDismissOnboarding() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/onboarding/dismiss")),
    onSuccess: (onboarding) => {
      client.setQueryData(ONBOARDING_KEY, onboarding);
    },
  });
}
