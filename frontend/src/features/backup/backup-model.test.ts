import { describe, expect, it } from "vitest";

import type { Backup, BackupRun, BackupSetup } from "@/features/backup/api";
import {
  BUSY_REFRESH_MS,
  IDLE_REFRESH_MS,
  OTHER_FOLDER,
  backupActivity,
  backupRefreshInterval,
  canBackUpNow,
  chosenFolder,
  initialFolderChoice,
  keyGroups,
  lastFailure,
  setupStep,
} from "@/features/backup/backup-model";

function run(overrides: Partial<BackupRun>): BackupRun {
  return {
    id: 1,
    started_at: "2026-10-11T10:00:00Z",
    finished_at: "2026-10-11T10:01:00Z",
    reason: "daily",
    status: "succeeded",
    snapshot_id: "a1",
    data_added: 1000,
    message: null,
    ...overrides,
  };
}

function backup(overrides: Partial<Backup>): Backup {
  return { state: "current", last_success: null, requested_at: null, runs: [], ...overrides };
}

describe("backupActivity", () => {
  it("is idle without a request", () => {
    expect(backupActivity(backup({ runs: [run({})] }))).toBe("idle");
    expect(backupActivity(backup({}))).toBe("idle");
  });

  it("waits for a requested backup", () => {
    const requested = backup({ requested_at: "2026-10-11T11:00:00Z", runs: [run({})] });
    expect(backupActivity(requested)).toBe("waiting");
    expect(backupActivity(backup({ requested_at: "2026-10-11T11:00:00Z" }))).toBe("waiting");
  });

  it("shows a running backup", () => {
    expect(backupActivity(backup({ runs: [run({ status: "running", finished_at: null })] }))).toBe(
      "running",
    );
  });

  it("allows another try when the requested backup failed", () => {
    const failed = run({ status: "failed", started_at: "2026-10-11T11:00:00Z", message: "no" });
    expect(backupActivity(backup({ requested_at: "2026-10-11T11:00:00Z", runs: [failed] }))).toBe(
      "idle",
    );
    // A failure before the request does not answer it.
    expect(backupActivity(backup({ requested_at: "2026-10-11T11:00:01Z", runs: [failed] }))).toBe(
      "waiting",
    );
  });
});

describe("backupRefreshInterval", () => {
  it("polls often only while something will change", () => {
    expect(backupRefreshInterval(undefined)).toBe(IDLE_REFRESH_MS);
    expect(backupRefreshInterval(backup({}))).toBe(IDLE_REFRESH_MS);
    expect(backupRefreshInterval(backup({ requested_at: "2026-10-11T11:00:00Z" }))).toBe(
      BUSY_REFRESH_MS,
    );
  });
});

describe("lastFailure", () => {
  it("is the message of the latest run if it failed", () => {
    expect(lastFailure(backup({}))).toBeNull();
    expect(lastFailure(backup({ runs: [run({})] }))).toBeNull();
    expect(
      lastFailure(backup({ runs: [run({ status: "failed", message: "unreachable" }), run({})] })),
    ).toBe("unreachable");
  });
});

const ONEDRIVE = "C:\\Users\\anna\\OneDrive\\Rhinvoice-Backup";
const DROPBOX = "C:\\Users\\anna\\Dropbox\\Rhinvoice-Backup";

function setup(overrides: Partial<BackupSetup>): BackupSetup {
  return {
    folder: null,
    suggestions: [
      { name: "OneDrive", path: ONEDRIVE },
      { name: "Dropbox", path: DROPBOX },
    ],
    key_confirmed: false,
    ...overrides,
  };
}

describe("setupStep", () => {
  it("chooses a folder, then confirms the key", () => {
    expect(setupStep(setup({}))).toBe("choose");
    expect(setupStep(setup({ key_confirmed: true }))).toBe("choose");
    expect(setupStep(setup({ folder: ONEDRIVE }))).toBe("key");
    expect(setupStep(setup({ folder: ONEDRIVE, key_confirmed: true }))).toBe("ready");
  });
});

describe("initialFolderChoice", () => {
  it("suggests the first cloud folder found", () => {
    expect(initialFolderChoice(setup({}))).toEqual({ choice: ONEDRIVE, other: "" });
    expect(initialFolderChoice(setup({ suggestions: [] }))).toEqual({
      choice: OTHER_FOLDER,
      other: "",
    });
  });

  it("keeps the folder in use", () => {
    expect(initialFolderChoice(setup({ folder: DROPBOX }))).toEqual({ choice: DROPBOX, other: "" });
    expect(initialFolderChoice(setup({ folder: "E:\\Backup" }))).toEqual({
      choice: OTHER_FOLDER,
      other: "E:\\Backup",
    });
  });
});

describe("chosenFolder", () => {
  it("is the suggested folder or the typed one", () => {
    expect(chosenFolder({ choice: ONEDRIVE, other: "E:\\Backup" })).toBe(ONEDRIVE);
    expect(chosenFolder({ choice: OTHER_FOLDER, other: "  E:\\Backup " })).toBe("E:\\Backup");
    expect(chosenFolder({ choice: OTHER_FOLDER, other: "  " })).toBeNull();
  });
});

describe("keyGroups", () => {
  it("splits the key where it is read aloud", () => {
    expect(keyGroups("K7QM-2XWP-9DTA")).toEqual(["K7QM", "2XWP", "9DTA"]);
  });
});

describe("canBackUpNow", () => {
  it("is refused until the first backup ran (no company yet, or no target)", () => {
    expect(canBackUpNow(backup({ state: "not_set_up" }))).toBe(false);
    expect(canBackUpNow(backup({ state: "current" }))).toBe(true);
    expect(canBackUpNow(backup({ state: "stale" }))).toBe(true);
  });
});
