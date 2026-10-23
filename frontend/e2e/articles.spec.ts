import { expect, expectAccessible, openApp, test, unique } from "./fixtures";

test("create an article with prices and find it", async ({ page, isMobile }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const name = `Beratung ${suffix}`;
  // The list offers a new article (not a new customer).
  await openApp(page, "/articles", "Artikel");
  await page
    .getByRole("link", { name: /^Neuer Artikel/ })
    .first()
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Neuer Artikel" })).toBeVisible();
  await page.getByLabel("Bezeichnung").fill(name);
  await page.getByLabel("Beschreibung").fill("Stundenansatz Senior");
  await page.getByLabel("Einheit").selectOption("HUR");
  await page.getByLabel("Preis in CHF").fill("1’234.5");
  await page.getByLabel("Preis in EUR").fill("1,2345");
  await page.getByLabel("Preis in EUR").blur();
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText(`Artikel «${name}» angelegt.`)).toBeVisible();
  await expect(page.getByLabel("Preis in CHF")).toHaveValue("1234.50");
  await expect(page.getByLabel("Preis in EUR")).toHaveValue("1.2345");

  await openApp(page, `/articles?q=${encodeURIComponent(name)}`, "Artikel");
  const row = page.getByRole("row").filter({ hasText: name });
  // Intl output differs between ICU versions (’ or '), so compare normalised text.
  const text = (await row.innerText()).replace(/[\u2019']/g, "'").replace(/\s+/g, " ");
  expect(text).toContain("CHF 1'234.50");
  // The EUR column is hidden on phones to keep the list readable.
  if (!isMobile) expect(text).toContain("EUR 1.2345");
  await expectAccessible(page);
});

test("article prices are validated", async ({ page }) => {
  await openApp(page, "/articles/new", "Neuer Artikel");
  await page.getByLabel("Bezeichnung").fill("Kabel");
  await page.getByLabel("Preis in CHF").fill("abc");
  await page.getByLabel("Preis in CHF").blur();
  await expect(page.getByText("Bitte geben Sie eine Zahl ein, z. B. 12.50.")).toBeVisible();
  await page.getByLabel("Preis in CHF").fill("1.23456");
  await page.getByLabel("Preis in CHF").blur();
  await expect(page.getByText("Höchstens 4 Nachkommastellen.")).toBeVisible();
  await expectAccessible(page);
});
