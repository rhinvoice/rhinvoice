import type { Page } from "@playwright/test";

import { expect, expectAccessible, openApp, test } from "./fixtures";

async function openAbout(page: Page, isMobile: boolean, account: string, about: RegExp) {
  if (isMobile) {
    await page.getByRole("button", { name: account }).click();
    await page.getByRole("menuitem", { name: about }).click();
  } else {
    await page.getByRole("button", { name: about }).click();
  }
}

test.describe("French and Italian interface", () => {
  test("switches to Français and Italiano and says they are machine translated", async ({
    page,
    isMobile,
  }) => {
    await openApp(page, "/", "Übersicht");

    // The menu names both languages in their own words, with the note in the same language.
    await page.getByRole("button", { name: "Sprache" }).click();
    const french = page.getByRole("menuitemradio", { name: "Français" });
    await expect(french).toHaveAccessibleDescription(
      "Traduction automatique – vos remarques sont les bienvenues",
    );
    await expect(page.getByRole("menuitemradio", { name: "Italiano" })).toHaveAccessibleDescription(
      "Traduzione automatica – segnalazioni benvenute",
    );
    await expect(page.getByRole("menuitemradio", { name: "English" })).not.toHaveAttribute(
      "aria-describedby",
    );
    // No axe run while the menu is open: the menu hides the page behind it (aria-hidden).
    await french.click();

    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Vue d’ensemble");
    await expect(page.locator("html")).toHaveAttribute("lang", "fr-CH");
    await expect(page).toHaveTitle("Vue d’ensemble · Rhinvoice");
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Vue d’ensemble");
    await expectAccessible(page);

    // The About dialog asks for corrections and leads to the problem report.
    await openAbout(page, isMobile, "Compte", /^À propos de Rhinvoice/);
    const about = page.getByRole("dialog", { name: "À propos de Rhinvoice" });
    await expect(about.getByText(/^Cette traduction a été réalisée automatiquement/)).toBeVisible();
    await expectAccessible(page);
    await about.getByRole("button", { name: "Signaler une erreur de traduction" }).click();
    await expect(page.getByRole("dialog", { name: "Signaler un problème" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Vue d’ensemble");

    await page.getByRole("button", { name: "Langue" }).click();
    await page.getByRole("menuitemradio", { name: "Italiano" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Panoramica");
    await expect(page.locator("html")).toHaveAttribute("lang", "it-CH");
    await expectAccessible(page);

    await openAbout(page, isMobile, "Account", /^Informazioni su Rhinvoice/);
    const informazioni = page.getByRole("dialog", { name: /^Informazioni su Rhinvoice/ });
    await expect(
      informazioni.getByRole("button", { name: "Segnala un errore di traduzione" }),
    ).toBeVisible();
    await expectAccessible(page);
  });
});

test.describe("browser language", () => {
  test.use({ storageState: { cookies: [], origins: [] }, locale: "it-IT" });

  test("greets an Italian browser in Swiss Italian on the login page", async ({ page }) => {
    await page.goto("/login");
    await expect(page).toHaveTitle("Accedi · Rhinvoice");
    await expect(page.locator("html")).toHaveAttribute("lang", "it-CH");
    await expect(page.getByRole("button", { name: "Accedi" })).toBeVisible();
    await expectAccessible(page);
  });
});
