import type { Page } from "@playwright/test";

import { expect, expectAccessible, HEADERS, openApp, test, unique } from "./fixtures";

/** The search for all customers answers as on a new installation: none yet. */
async function noCustomersYet(page: Page): Promise<void> {
  await page.route("**/api/customers?*", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() !== "GET" || (url.searchParams.get("q") ?? "") !== "") {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...body, items: [], total: 0 } });
  });
}

/** Other tests expect no EUR account (issuing in EUR then waits for one). */
async function deleteEuroAccounts(page: Page): Promise<void> {
  const accounts = (await (await page.request.get("/api/bank-accounts")).json()) as {
    id: string;
    currency: string;
  }[];
  for (const account of accounts.filter((each) => each.currency === "EUR")) {
    await page.request.delete(`/api/bank-accounts/${account.id}`, { headers: HEADERS });
  }
}

test.afterEach(async ({ page }) => {
  await deleteEuroAccounts(page);
});

test("a first invoice gets its customer, article and bank account without leaving the editor", async ({
  page,
}, testInfo) => {
  // Also new on a second run against the same database.
  const suffix = `${unique(testInfo.project.name)} ${Date.now().toString(36)}`;
  const customerName = `Gartenbau ${suffix}`;
  const articleName = `Rasenpflege ${suffix}`;
  await noCustomersYet(page);
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await expect(page.getByText("Noch keine Kunden.")).toBeVisible();
  await expectAccessible(page);

  // 1. The customer, from what was typed in the search.
  await page.getByRole("combobox", { name: "Kunde suchen" }).fill(customerName);
  await page.getByRole("option", { name: `«${customerName}» als neuen Kunden anlegen` }).click();
  const sheet = page.getByRole("dialog", { name: "Neuer Kunde" });
  await expect(sheet.getByLabel("Firmenname")).toHaveValue(customerName);
  await sheet.getByLabel("Strasse").fill("Gartenweg");
  await sheet.getByLabel(/^Nr\./).fill("3");
  await sheet.getByLabel("PLZ").fill("8400");
  await sheet.getByLabel("Ort").fill("Winterthur");
  await expectAccessible(page);
  await sheet.getByRole("button", { name: "Anlegen und wählen" }).click();
  await expect(sheet).toBeHidden();
  await expect(page.getByText(`Kunde «${customerName}» angelegt.`)).toBeVisible();
  await expect(page.getByText("Noch keine Kunden.")).toBeHidden();
  await expect(page.getByText(customerName, { exact: true })).toBeVisible();

  // 2. The typed position, kept as an article for the next time.
  await page.locator("#lines-0-description").fill(articleName);
  await page.locator("#lines-0-unit_price").fill("85");
  await page.getByLabel("Als Artikel speichern").check();
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(
    page.getByText(new RegExp(`^Artikel \\S+ «${articleName}» gespeichert\\.$`)),
  ).toBeVisible();

  // 3. What issuing needs, collected on top and filled in right there.
  await page.getByText("Weitere Angaben", { exact: true }).click();
  await page.getByLabel("Währung").selectOption("EUR");
  const missing = page.getByRole("region", { name: "Vor dem Ausstellen fehlt noch:" });
  await expect(missing.getByText("ein Bankkonto in EUR für die Zahlungsangaben")).toBeVisible();
  await expectAccessible(page);
  await missing.getByRole("button", { name: "EUR-Konto erfassen" }).click();
  const account = page.getByRole("dialog", { name: "Konto hinzufügen" });
  await expect(account.getByRole("combobox", { name: "Währung" })).toHaveValue("EUR");
  await account.getByLabel("Bank", { exact: true }).fill("Musterbank");
  await account.getByLabel("IBAN", { exact: true }).fill("CH56 0483 5012 3456 7800 9");
  await account.getByRole("button", { name: "Speichern" }).click();
  await expect(account).toBeHidden();
  await expect(missing).toBeHidden();

  // Keyboard, as on phones the toasts may lie over the save bar.
  await page.getByRole("button", { name: "Ausstellen" }).focus();
  await page.keyboard.press("Enter");
  const confirm = page.getByRole("alertdialog", { name: "Rechnung ausstellen?" });
  await confirm.getByRole("button", { name: "Ausstellen" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/^Rechnung .+ ausgestellt\.$/)).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: /^Rechnung \S+$/ })).toBeVisible();

  // The article is found by the line search of the next invoice.
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await page.locator("#lines-0-description").fill(articleName.slice(0, 8));
  await expect(page.getByRole("option", { name: new RegExp(articleName) })).toBeVisible();
});
