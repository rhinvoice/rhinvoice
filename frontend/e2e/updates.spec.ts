import type { Page } from "@playwright/test";

import { expect, expectAccessible, openApp, test } from "./fixtures";

/** A newer release as GET /api/updates reports it (ADR 0022). */
function release(overrides: Record<string, unknown>) {
  return {
    current: "0.6.2",
    latest: "0.7.0",
    action: "install",
    notes_url: "https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
    setup_url: null,
    checked_at: "2026-10-14T09:00:00Z",
    failed: false,
    can_check: true,
    setup: null,
    ...overrides,
  };
}

/** The navigation with the notice: the sidebar, or the menu on a phone. */
async function showNavigation(page: Page): Promise<void> {
  const menu = page.getByRole("button", { name: "Menü öffnen" });
  if (await menu.isVisible()) {
    await menu.click();
  }
}

test("the installation without Docker installs a new version with one click", async ({ page }) => {
  let installed = false;
  await page.route("**/api/updates/install", async (route) => {
    installed = true;
    await route.fulfill({ status: 202, json: release({}) });
  });
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({}) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  const notice = page.getByRole("region", { name: "Aktualisierung" });
  await expect(notice.getByText("Neue Version 0.7.0")).toBeVisible();
  await expect(notice.getByRole("link", { name: /Was ist neu\?/ })).toHaveAttribute(
    "href",
    "https://github.com/rhinvoice/rhinvoice/releases/tag/v0.7.0",
  );
  await expectAccessible(page);
  await notice.getByRole("button", { name: "Jetzt aktualisieren" }).click();
  // Asked first (ADR 0031): the program restarts, the user saves before.
  const ask = page.getByRole("alertdialog", { name: "Rhinvoice für das Update schließen?" });
  await expect(ask).toContainText("Speichern Sie vorher alles");
  await expectAccessible(page);
  await ask.getByRole("button", { name: "Später" }).click();
  expect(installed).toBe(false);
  await notice.getByRole("button", { name: "Jetzt aktualisieren" }).click();
  await ask.getByRole("button", { name: "Schließen und aktualisieren" }).click();
  // The program restarts; the page waits for the new version and then loads it.
  await expect(notice.getByRole("status")).toHaveText("Rhinvoice startet neu …");
  expect(installed).toBe(true);
});

test("a server installation is told the version line and the command", async ({ page }) => {
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({ action: "command" }) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  const notice = page.getByRole("region", { name: "Aktualisierung" });
  await expect(notice.getByText("RHINVOICE_VERSION=0.7.0")).toBeVisible();
  await expect(notice.getByText("docker compose pull && docker compose up -d")).toBeVisible();
  await expect(notice.getByRole("button", { name: "Jetzt aktualisieren" })).toHaveCount(0);
  await expectAccessible(page);
});

test("an update that was taken back says which version runs again", async ({ page }) => {
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({ action: "none", failed: true }) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  const notice = page.getByRole("region", { name: "Aktualisierung" });
  await expect(notice.getByText("Das Update auf 0.7.0 hat nicht funktioniert")).toBeVisible();
  await expect(notice.getByText("Rhinvoice 0.6.2 läuft wieder")).toBeVisible();
  await expectAccessible(page);
});

test("About Rhinvoice tells whether this is the newest version", async ({ page }) => {
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({ current: "0.7.0", action: "none" }) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  await expect(page.getByRole("region", { name: "Aktualisierung" })).toHaveCount(0);
  await page.locator("[data-app-version]:visible").first().click();
  const about = page.getByRole("dialog", { name: "Über Rhinvoice" });
  await expect(about.getByText("Rhinvoice ist auf dem neuesten Stand.")).toBeVisible();
  await expectAccessible(page);
});

test("About Rhinvoice checks for a new version on request", async ({ page }) => {
  let checked = false;
  await page.route("**/api/updates/check", async (route) => {
    checked = true;
    await route.fulfill({ json: release({}) });
  });
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({ current: "0.7.0", action: "none" }) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  await page.locator("[data-app-version]:visible").first().click();
  const about = page.getByRole("dialog", { name: "Über Rhinvoice" });
  await about.getByRole("button", { name: "Nach Updates suchen" }).click();
  await expect(about.getByText("Neue Version 0.7.0")).toBeVisible();
  await expect(about.getByRole("button", { name: "Jetzt aktualisieren" })).toBeVisible();
  expect(checked).toBe(true);
  await expectAccessible(page);
});

test("a failed check says why", async ({ page }) => {
  await page.route("**/api/updates/check", async (route) => {
    await route.fulfill({
      status: 503,
      json: { error: { code: "update_check_failed", message: "offline", details: {} } },
    });
  });
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({ current: "0.7.0", action: "none" }) });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  await page.locator("[data-app-version]:visible").first().click();
  const about = page.getByRole("dialog", { name: "Über Rhinvoice" });
  await about.getByRole("button", { name: "Nach Updates suchen" }).click();
  await expect(about.getByRole("alert")).toContainText("nicht abgerufen werden");
  await expectAccessible(page);
});

test("a new setup is downloaded in the program and run after asking", async ({ page }) => {
  // ADR 0031: no browser, no Downloads folder; the program closes for the setup.
  let setup = { state: "idle", received: 0, total: 58_000_000 };
  let ran = false;
  const needsSetup = () =>
    release({
      action: "setup",
      setup_url: "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/Setup.exe",
      setup,
    });
  await page.route("**/api/updates/setup/download", async (route) => {
    setup = { state: "downloading", received: 22_000_000, total: 58_000_000 };
    await route.fulfill({ status: 202, json: needsSetup() });
  });
  await page.route("**/api/updates/setup/run", async (route) => {
    ran = true;
    await route.fulfill({ status: 202, json: needsSetup() });
  });
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: needsSetup() });
  });
  await openApp(page, "/", "Übersicht");
  await showNavigation(page);
  const notice = page.getByRole("region", { name: "Aktualisierung" });
  await expect(notice.getByText("0.7.0 braucht ein neues Setup")).toBeVisible();
  await notice.getByRole("button", { name: "Jetzt aktualisieren" }).click();
  const ask = page.getByRole("alertdialog", { name: "Rhinvoice für das Update schließen?" });
  await expect(ask.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "37");
  await expect(ask.getByText("Wird heruntergeladen … 22 von 58 MB")).toBeVisible();
  await expect(ask.getByRole("button", { name: "Schließen und aktualisieren" })).toBeDisabled();
  await expectAccessible(page);
  setup = { state: "ready", received: 58_000_000, total: 58_000_000 };
  await expect(ask.getByRole("button", { name: "Schließen und aktualisieren" })).toBeEnabled();
  await ask.getByRole("button", { name: "Schließen und aktualisieren" }).click();
  await expect(notice.getByRole("status")).toHaveText(
    "Rhinvoice wird für das Update geschlossen …",
  );
  expect(ran).toBe(true);
});

test("closing for an update warns about unsaved changes", async ({ page }) => {
  await page.route("**/api/updates", async (route) => {
    await route.fulfill({ json: release({}) });
  });
  await openApp(page, "/settings", "Einstellungen");
  await page.getByLabel("Firmenname").fill("Noch nicht gespeichert AG");
  await showNavigation(page);
  const notice = page.getByRole("region", { name: "Aktualisierung" });
  await notice.getByRole("button", { name: "Jetzt aktualisieren" }).click();
  const ask = page.getByRole("alertdialog", { name: "Rhinvoice für das Update schließen?" });
  await expect(ask.getByText("Es gibt noch ungespeicherte Änderungen.")).toBeVisible();
  await expect(ask.getByRole("button", { name: "Trotzdem schließen" })).toBeVisible();
  await expectAccessible(page);
  await ask.getByRole("button", { name: "Später" }).click();
  await expect(page.getByLabel("Firmenname")).toHaveValue("Noch nicht gespeichert AG");
});
