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

type BackupSetup = components["schemas"]["BackupSetupResponse"];

/** choose: no folder yet; key: the key is not confirmed as kept; ready: backups run. */
export type SetupStep = "choose" | "key" | "ready";

export function setupStep(setup: BackupSetup): SetupStep {
  if (setup.folder === null) {
    return "choose";
  }
  return setup.key_confirmed ? "ready" : "key";
}

/** The radio value of "another folder", next to the paths of the suggested folders. */
export const OTHER_FOLDER = "other";

export interface FolderChoice {
  readonly choice: string;
  readonly other: string;
}

/** Start with the folder in use, else the first cloud folder found. */
export function initialFolderChoice(setup: BackupSetup): FolderChoice {
  const suggested = setup.suggestions.map((suggestion) => suggestion.path);
  if (setup.folder !== null) {
    return suggested.includes(setup.folder)
      ? { choice: setup.folder, other: "" }
      : { choice: OTHER_FOLDER, other: setup.folder };
  }
  return { choice: suggested[0] ?? OTHER_FOLDER, other: "" };
}

/** The folder to back up into, or null while "another folder" is still empty. */
export function chosenFolder({ choice, other }: FolderChoice): string | null {
  if (choice !== OTHER_FOLDER) {
    return choice;
  }
  const typed = other.trim();
  return typed === "" ? null : typed;
}

/** The key in its groups (K7QM-2XWP-… becomes K7QM, 2XWP, …), shown as a grid. */
export function keyGroups(key: string): string[] {
  return key.split("-");
}
