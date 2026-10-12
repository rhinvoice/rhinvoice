import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { backupRefreshInterval } from "@/features/backup/backup-model";

export type Backup = components["schemas"]["BackupResponse"];
export type BackupRun = components["schemas"]["BackupRunResponse"];

const BACKUP_KEY = ["backup"];

export const backupQuery = queryOptions({
  queryKey: BACKUP_KEY,
  queryFn: () => unwrap(api.GET("/api/backup")),
  refetchInterval: (query) => backupRefreshInterval(query.state.data),
});

export function useRequestBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/backup")),
    onSuccess: (backup) => {
      client.setQueryData(BACKUP_KEY, backup);
    },
  });
}
