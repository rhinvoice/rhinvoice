import type { components } from "@/api/client";

type Backup = components["schemas"]["BackupResponse"];

/** idle: nothing to wait for; waiting: requested, not started; running: a backup runs. */
export type BackupActivity = "idle" | "waiting" | "running";

/** While a backup is requested or running the state changes within seconds. */
export const BUSY_REFRESH_MS = 5_000;
/** Otherwise once a minute: "vor 3 Minuten" stays true and daily backups show up. */
export const IDLE_REFRESH_MS = 60_000;

export function backupActivity(backup: Backup): BackupActivity {
  const latest = backup.runs[0];
  if (latest?.status === "running") {
    return "running";
  }
  if (backup.requested_at === null) {
    return "idle";
  }
  // A request stays open after a failed attempt and is retried later (backup container);
  // until then it may be tried again by hand.
  const failedSince =
    latest?.status === "failed" && Date.parse(latest.started_at) >= Date.parse(backup.requested_at);
  return failedSince ? "idle" : "waiting";
}

export function backupRefreshInterval(backup: Backup | undefined): number {
  return backup !== undefined && backupActivity(backup) !== "idle"
    ? BUSY_REFRESH_MS
    : IDLE_REFRESH_MS;
}

/** The message of the latest run if it failed. */
export function lastFailure(backup: Backup): string | null {
  const latest = backup.runs[0];
  return latest?.status === "failed" ? latest.message : null;
}
