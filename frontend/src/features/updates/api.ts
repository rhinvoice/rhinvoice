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

export function useInstallUpdate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/updates/install")),
    onSuccess: (update) => {
      client.setQueryData(UPDATES_KEY, update);
    },
  });
}
