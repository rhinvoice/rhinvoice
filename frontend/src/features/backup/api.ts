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

export type BackupSetup = components["schemas"]["BackupSetupResponse"];

const SETUP_KEY = ["backup", "setup"];
const RECOVERY_KEY = ["backup", "key"];

/**
 * Folder and key of the installation without Docker (ADR 0023). In the Docker setup the
 * API answers 409 backup_by_container: the backup container is set up instead.
 */
export const backupSetupQuery = queryOptions({
  queryKey: SETUP_KEY,
  queryFn: () => unwrap(api.GET("/api/backup/setup")),
  retry: false,
});

export const recoveryKeyQuery = queryOptions({
  queryKey: RECOVERY_KEY,
  queryFn: () => unwrap(api.GET("/api/backup/key")),
  // The key never changes by itself; it is fetched when shown.
  staleTime: Infinity,
  gcTime: 0,
});

/** Back up into a folder; returns the recovery key, the first backup is requested. */
export function useSetUpBackups() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (folder: string) => unwrap(api.PUT("/api/backup/setup", { body: { folder } })),
    onSuccess: (key) => {
      client.setQueryData(RECOVERY_KEY, key);
      void client.invalidateQueries({ queryKey: BACKUP_KEY });
    },
  });
}

export function useConfirmRecoveryKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/backup/key/confirmed")),
    onSuccess: (setup) => {
      client.setQueryData(SETUP_KEY, setup);
    },
  });
}

export function useRequestBackup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/backup")),
    onSuccess: (backup) => {
      client.setQueryData(BACKUP_KEY, backup);
    },
  });
}
