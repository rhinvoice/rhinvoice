import type { components } from "@/api/client";
import { REPOSITORY_URL } from "@/lib/about";

export type Update = components["schemas"]["UpdateResponse"];
/** The new setup as the program downloads it itself (ADR 0031). */
export type SetupDownload = components["schemas"]["SetupResponse"];

/** What the notice at the foot of the navigation says (ADR 0022); null: nothing. */
export type UpdateNotice =
  | { readonly kind: "install"; readonly version: string; readonly notesUrl: string | null }
  | {
      readonly kind: "command";
      readonly version: string;
      readonly notesUrl: string | null;
      readonly envLine: string;
      readonly command: string;
    }
  | {
      readonly kind: "setup";
      readonly version: string;
      readonly notesUrl: string | null;
      readonly setupUrl: string;
      /** null: the setup is downloaded by hand from setupUrl (releases before ADR 0031). */
      readonly download: SetupDownload | null;
    }
  | { readonly kind: "failed"; readonly version: string; readonly current: string };

export const DOCKER_COMMAND = "docker compose pull && docker compose up -d";
export const RELEASES_URL = `${REPOSITORY_URL}/releases`;

/** The server checks once a day; the page asks it once an hour. */
export const CHECK_INTERVAL_MS = 60 * 60 * 1000;
/** While the program restarts after an update. */
export const RESTART_POLL_MS = 2_000;
/** The server's first check runs half a minute after the start; until then the page asks
 * again this often, but only for the first answers (with the check off it never comes). */
export const FIRST_CHECK_POLL_MS = 15_000;
export const FIRST_CHECK_POLLS = 20;
/** While the program downloads a setup, for its progress. */
export const SETUP_POLL_MS = 1_000;

/** The line in .env that pins the version of a Docker installation. */
export function envLine(version: string): string {
  return `RHINVOICE_VERSION=${version}`;
}

export function updateNotice(update: Update | undefined): UpdateNotice | null {
  const version = update?.latest ?? null;
  if (update === undefined || version === null) {
    return null;
  }
  if (update.failed) {
    return { kind: "failed", version, current: update.current };
  }
  switch (update.action) {
    case "install":
      return { kind: "install", version, notesUrl: update.notes_url };
    case "command":
      return {
        kind: "command",
        version,
        notesUrl: update.notes_url,
        envLine: envLine(version),
        command: DOCKER_COMMAND,
      };
    case "setup":
      return {
        kind: "setup",
        version,
        notesUrl: update.notes_url,
        setupUrl: update.setup_url ?? RELEASES_URL,
        download: update.setup,
      };
    case "none":
      return null;
  }
}

/** How long the page waits before it asks the server again. */
export function checkInterval(update: Update | undefined, answers: number): number {
  if (update?.setup?.state === "downloading") {
    return SETUP_POLL_MS;
  }
  const unchecked = (update?.checked_at ?? null) === null;
  return unchecked && answers < FIRST_CHECK_POLLS ? FIRST_CHECK_POLL_MS : CHECK_INTERVAL_MS;
}

/** Whether the program answers with another version than before the update. */
export function restartedInto(before: string, update: Update | undefined): boolean {
  return update !== undefined && update.current !== before;
}

/** How much of the setup has come, in whole percent. */
export function downloadPercent(download: SetupDownload): number {
  return download.total === 0 ? 0 : Math.floor((download.received / download.total) * 100);
}

/** Bytes as whole megabytes, for "38 of 58 MB". */
export function megabytes(bytes: number): number {
  return Math.round(bytes / 1_000_000);
}
