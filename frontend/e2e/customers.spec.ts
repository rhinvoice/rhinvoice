import { waitForToastsToClose, expect, expectAccessible, openApp, test, unique } from "./fixtures";

test("create, find, edit and archive a customer", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const name = `Müller ${suffix} AG`;
  await openApp(page, "/customers", "Kunden");
  await page
    .getByRole("link", { name: /Neuer Kunde/ })
    .first()
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Neuer Kunde" })).toBeVisible();

  await page.getByRole("button", { name: "Speichern" }).click();
  const summary = page.getByRole("alert").filter({ hasText: "korrigiert werden" });
  await expect(summary).toBeFocused();
  await expectAccessible(page);

  await page.getByLabel("Firmenname").fill(name);
  await page.getByLabel("Kontaktperson").fill("Frau Muster");
  await page.getByLabel("Strasse").fill("Marktgasse");
  await page.getByLabel(/^Nr\./).fill("5");
  await page.getByLabel("PLZ").fill("3011");
  await page.getByLabel("Ort").fill("Bern");
  await page.getByLabel("E-Mail").fill(`info@${suffix}.example`);
  await page.getByLabel("Standard-Rabatt in %").fill("2,5");
  await page.getByRole("button", { name: "Speichern" }).click();

  await expect(page.getByText(`Kunde «${name}» angelegt.`)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.getByLabel("Standard-Rabatt in %")).toHaveValue("2.5");

  await page.getByLabel("Ort").fill("Bern-Bümpliz");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Kunden" }).first().click();
  await page.getByRole("searchbox", { name: "Kunden durchsuchen" }).fill(`muller ${suffix}`);
  const row = page.getByRole("row").filter({ hasText: name });
  await expect(row).toBeVisible();
  await expect(page.getByText("1 Treffer")).toBeVisible();
  await expect(page).toHaveURL(/q=muller/);
  await waitForToastsToClose(page);
  await expect(page).toHaveScreenshot("customer-list.png", {
    mask: [page.locator("td:first-child")],
  });
  await expectAccessible(page);

  await row.getByRole("link", { name }).click();
  await page.getByRole("button", { name: "Archivieren" }).click();
  await expect(page.getByText(`«${name}» archiviert.`)).toBeVisible();
  await expect(page.getByText("Dieser Kunde ist archiviert")).toBeVisible();
  await page.getByRole("button", { name: "Rückgängig" }).click();
  await expect(page.getByRole("button", { name: "Archivieren" })).toBeVisible();
});

test("customer form switches between company and person", async ({ page }) => {
  await openApp(page, "/customers/new", "Neuer Kunde");
  await expect(page.getByLabel("Firmenname")).toBeVisible();
  await page.getByLabel("Privatperson").check();
  await expect(page.getByLabel("Firmenname")).toBeHidden();
  await expect(page.getByLabel("Nachname")).toBeVisible();
  await page.getByLabel("Abweichende Lieferadresse").click();
  await expect(page.getByLabel("PLZ")).toHaveCount(2);
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("customer-form.png");
});

test("the C key opens a new customer", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcuts are a desktop feature");
  await openApp(page, "/customers", "Kunden");
  await page.keyboard.press("c");
  await expect(page).toHaveURL(/\/customers\/new$/);
});
