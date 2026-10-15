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
