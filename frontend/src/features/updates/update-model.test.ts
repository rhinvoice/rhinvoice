import { describe, expect, it } from "vitest";

import {
  CHECK_INTERVAL_MS,
  DOCKER_COMMAND,
  FIRST_CHECK_POLLS,
  FIRST_CHECK_POLL_MS,
  RELEASES_URL,
  SETUP_POLL_MS,
  checkInterval,
  downloadPercent,
  megabytes,
  envLine,
  restartedInto,
  updateNotice,
  type Update,
} from "@/features/updates/update-model";

const NOTES = "https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0";

function update(overrides: Partial<Update> = {}): Update {
  return {
    current: "0.6.2",
    latest: "0.7.0",
    action: "install",
    notes_url: NOTES,
    setup_url: null,
    checked_at: "2026-10-14T09:00:00Z",
    failed: false,
    can_check: true,
    setup: null,
    ...overrides,
  };
}

describe("updateNotice", () => {
  it("says nothing before the first check or when this is the newest version", () => {
    expect(updateNotice(undefined)).toBeNull();
    expect(updateNotice(update({ action: "none" }))).toBeNull();
    expect(updateNotice(update({ latest: null, action: "none" }))).toBeNull();
  });

  it("offers the installation without Docker to install it", () => {
    expect(updateNotice(update())).toEqual({ kind: "install", version: "0.7.0", notesUrl: NOTES });
  });

  it("tells a server installation the version line and the command", () => {
    expect(updateNotice(update({ action: "command" }))).toEqual({
      kind: "command",
      version: "0.7.0",
      notesUrl: NOTES,
      envLine: "RHINVOICE_VERSION=0.7.0",
      command: DOCKER_COMMAND,
    });
  });

  it("leads to the setup when the release needs a new one", () => {
    const setup =
      "https://github.com/rhinvoice/rhinvoice/releases/download/v0.9.0/Rhinvoice-Setup-0.9.0.exe";
    expect(updateNotice(update({ latest: "0.9.0", action: "setup", setup_url: setup }))).toEqual({
      kind: "setup",
      version: "0.9.0",
      notesUrl: NOTES,
      setupUrl: setup,
      download: null,
    });
    // Without a setup for this platform: the releases page.
    expect(updateNotice(update({ action: "setup" }))).toMatchObject({ setupUrl: RELEASES_URL });
  });

  it("lets the program download the setup itself when it can (ADR 0031)", () => {
    const download = { state: "downloading" as const, received: 5, total: 10 };
    expect(updateNotice(update({ action: "setup", setup: download }))).toMatchObject({
      kind: "setup",
      download,
    });
  });

  it("says that an update did not work and which version runs again", () => {
    expect(updateNotice(update({ action: "none", failed: true }))).toEqual({
      kind: "failed",
      version: "0.7.0",
      current: "0.6.2",
    });
  });

  it("does not repeat a failure about a release it does not know", () => {
    expect(updateNotice(update({ latest: null, action: "none", failed: true }))).toBeNull();
  });
});

describe("checkInterval", () => {
  it("asks again soon while the server has not checked yet", () => {
    expect(checkInterval(undefined, 0)).toBe(FIRST_CHECK_POLL_MS);
    expect(checkInterval(update({ checked_at: null }), 1)).toBe(FIRST_CHECK_POLL_MS);
  });

  it("asks once an hour after the first check", () => {
    expect(checkInterval(update(), 1)).toBe(CHECK_INTERVAL_MS);
  });

  it("stops asking often when the check never comes (switched off, offline)", () => {
    expect(checkInterval(update({ checked_at: null }), FIRST_CHECK_POLLS - 1)).toBe(
      FIRST_CHECK_POLL_MS,
    );
    expect(checkInterval(update({ checked_at: null }), FIRST_CHECK_POLLS)).toBe(CHECK_INTERVAL_MS);
  });
});

describe("checkInterval while a setup downloads", () => {
  it("asks every second for the progress", () => {
    const downloading = update({
      action: "setup",
      setup: { state: "downloading", received: 1, total: 2 },
    });
    expect(checkInterval(downloading, 99)).toBe(SETUP_POLL_MS);
    const ready = update({ action: "setup", setup: { state: "ready", received: 2, total: 2 } });
    expect(checkInterval(ready, 99)).toBe(CHECK_INTERVAL_MS);
  });
});

describe("downloadPercent and megabytes", () => {
  it("tell the progress in whole numbers", () => {
    expect(downloadPercent({ state: "downloading", received: 38_500_000, total: 58_000_000 })).toBe(
      66,
    );
    expect(downloadPercent({ state: "idle", received: 0, total: 0 })).toBe(0);
    expect(megabytes(58_080_402)).toBe(58);
    expect(megabytes(499_999)).toBe(0);
  });
});

describe("restartedInto", () => {
  it("notices when the program answers with another version", () => {
    expect(restartedInto("0.6.2", update({ current: "0.6.2" }))).toBe(false);
    expect(restartedInto("0.6.2", undefined)).toBe(false);
    expect(restartedInto("0.6.2", update({ current: "0.7.0" }))).toBe(true);
  });
});

describe("envLine", () => {
  it("pins the version in .env", () => {
    expect(envLine("0.7.0")).toBe("RHINVOICE_VERSION=0.7.0");
  });
});
