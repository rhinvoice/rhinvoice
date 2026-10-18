import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";
import { CHECK_INTERVAL_MS, checkInterval } from "@/features/updates/update-model";

const UPDATES_KEY = ["updates"];

export const updatesQuery = queryOptions({
  queryKey: UPDATES_KEY,
  queryFn: () => unwrap(api.GET("/api/updates")),
  refetchInterval: (query) => checkInterval(query.state.data, query.state.dataUpdateCount),
  staleTime: CHECK_INTERVAL_MS,
});

/** Asks for the newest release now instead of waiting for the daily check. */
export function useCheckUpdates() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/updates/check")),
    onSuccess: (update) => {
      client.setQueryData(UPDATES_KEY, update);
    },
  });
}

export function useInstallUpdate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/updates/install")),
    onSuccess: (update) => {
      client.setQueryData(UPDATES_KEY, update);
    },
  });
}

/** Starts downloading the new setup; the status then tells the progress (ADR 0031). */
export function useDownloadSetup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/updates/setup/download")),
    onSuccess: (update) => {
      client.setQueryData(UPDATES_KEY, update);
    },
  });
}

/** Starts the downloaded setup; the program closes right after. */
export function useRunSetup() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/updates/setup/run")),
  });
}
