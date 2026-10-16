import type { Page } from "@playwright/test";

import { expect, expectAccessible, openApp, test } from "./fixtures";

/** GET /api/support/report of the program for Windows and Mac, or of a server. */
function supportReport(overrides: Record<string, unknown>) {
  return {
    version: "0.7.4",
    system: "Windows 11 (AMD64)",
    installation: "desktop",
    log: "INFO: started\nERROR: no printer",
    ...overrides,
  };
}

/** About Rhinvoice, from the version in the navigation (the menu on a phone). */
async function openReport(page: Page) {
  const menu = page.getByRole("button", { name: "Menü öffnen" });
  if (await menu.isVisible()) {
    await menu.click();
  }
  await page.locator("[data-app-version]:visible").first().click();
  await page
    .getByRole("dialog", { name: "Über Rhinvoice" })
    .getByRole("button", { name: "Problem melden" })
    .click();
  return page.getByRole("dialog", { name: "Problem melden" });
}

test("a problem report copies the log and leads to GitHub", async ({ page }) => {
  await page.addInitScript(() => {
    // The clipboard of the test browser: what was copied stays readable.
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: (text: string) => {
          (window as unknown as { copied: string }).copied = text;
          return Promise.resolve();
        },
      },
    });
  });
  await page.route("**/api/support/report", async (route) => {
    await route.fulfill({ json: supportReport({}) });
  });
  await openApp(page, "/", "Übersicht");
  const report = await openReport(page);
  await expect(report.getByText("Es kann Namen von Kunden enthalten")).toBeVisible();
  await expectAccessible(page);
  await report.getByRole("button", { name: "Protokoll kopieren" }).click();
  await expect(report.getByRole("button", { name: "Protokoll kopiert" })).toBeVisible();
  const copied = await page.evaluate(() => (window as unknown as { copied: string }).copied);
  expect(copied).toContain("Rhinvoice 0.7.4 · Windows 11 (AMD64)");
  expect(copied).toContain("ERROR: no printer");
  await expect(report.getByText("hello@rhinvoice.com")).toBeVisible();
  await expect(report.getByRole("link", { name: /Auf GitHub melden/ })).toHaveAttribute(
    "href",
    /issues\/new\?template=bug_report\.yml&version=0\.7\.4/,
  );
});

test("a server tells where its log is", async ({ page }) => {
  await page.route("**/api/support/report", async (route) => {
    await route.fulfill({
      json: supportReport({ installation: "server", system: "Linux 6.8 (x86_64)", log: null }),
    });
  });
  await openApp(page, "/", "Übersicht");
  const report = await openReport(page);
  await expect(report.getByText("docker compose logs --tail 200 app")).toBeVisible();
  await expect(report.getByRole("button", { name: "Protokoll kopieren" })).toHaveCount(0);
  await expectAccessible(page);
});
