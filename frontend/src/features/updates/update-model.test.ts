import { describe, expect, it } from "vitest";

import {
  DOCKER_COMMAND,
  RELEASES_URL,
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
    });
    // Without a setup for this platform: the releases page.
    expect(updateNotice(update({ action: "setup" }))).toMatchObject({ setupUrl: RELEASES_URL });
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
