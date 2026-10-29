import type { Page } from "@playwright/test";

import {
  createCustomer,
  expect,
  expectAccessible,
  HEADERS,
  openApp,
  test,
  unique,
} from "./fixtures";

/**
 * Remove the CHF accounts a test added: with one CHF account the editor offers no
 * choice, which other tests (and their screenshots) expect.
 */
async function removeAddedAccounts(page: Page): Promise<void> {
  const accounts = (await (await page.request.get("/api/bank-accounts")).json()) as {
    id: string;
    currency: string;
    bank_name: string;
    qr_iban: string | null;
    third_party: boolean;
  }[];
  for (const account of accounts) {
    if (account.currency === "CHF" && (account.qr_iban !== null || account.third_party)) {
      await page.request.delete(`/api/bank-accounts/${account.id}`, { headers: HEADERS });
    }
  }
}

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg==",
  "base64",
);

test.describe.configure({ mode: "serial" });

test("company details can be saved", async ({ page }) => {
  await openApp(page, "/settings", "Einstellungen");
  await expect(page.getByRole("tab", { name: "Firma", selected: true })).toBeVisible();
  // Earlier projects may already have saved the company: start from an invalid state.
  await page.getByLabel("Firmenname").fill("");
  await page.getByRole("button", { name: "Speichern" }).click();
  const summary = page.getByRole("alert").filter({ hasText: "korrigiert werden" });
  // Each entry names its field: "Bitte ausfüllen." alone does not say which one.
  await expect(summary.getByRole("link", { name: "Firmenname: Bitte ausfüllen." })).toBeVisible();

  await page.getByLabel("Firmenname").fill("Muster GmbH");
  await page.getByLabel("Strasse").fill("Bahnhofstrasse");
  await page.getByLabel(/^Nr\./).fill("1");
  await page.getByLabel("PLZ").fill("8001");
  await page.getByLabel("Ort").fill("Zürich");
  await page.getByLabel("UID / MWST-Nummer").fill("CHE-123.456.789");
  await page.getByLabel("UID / MWST-Nummer").blur();
  await expect(page.locator("#vat_number-message")).toHaveText(
    "Die Prüfziffer der UID stimmt nicht – bitte prüfen.",
  );
  await page.getByLabel("UID / MWST-Nummer").fill("CHE-123.456.788 MWST");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Firmendaten gespeichert.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Firmenname")).toHaveValue("Muster GmbH");
  await expectAccessible(page);
});

test("the logo can be uploaded and removed", async ({ page }) => {
  await openApp(page, "/settings", "Einstellungen");
  await page
    .locator("#logo-file")
    .setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: PNG });
  await expect(page.getByText("Logo gespeichert.")).toBeVisible();
  await expect(page.getByRole("img", { name: "Aktuelles Firmenlogo" })).toBeVisible();
  await page.getByRole("button", { name: "Logo entfernen" }).click();
  await expect(page.getByRole("img", { name: "Aktuelles Firmenlogo" })).toBeHidden();
});

test("bank accounts validate the IBAN", async ({ page }) => {
  await openApp(page, "/settings?tab=bank-accounts", "Einstellungen");
  const add = page.getByRole("button", { name: "Konto hinzufügen" }).first();
  await add.click();
  const dialog = page.getByRole("dialog", { name: /Konto hinzufügen/ });
  await dialog.getByLabel("Bank", { exact: true }).fill("Musterbank");
  await dialog.getByLabel("IBAN", { exact: true }).fill("CH93 0076 2011 6238 5295 8");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(
    dialog.getByText("Die Prüfziffern stimmen nicht – bitte auf Tippfehler prüfen."),
  ).toBeVisible();
  await expectAccessible(page);
  // A Swiss euro account needs its BIC for the EPC QR code to customers in the EU.
  const bicHint = dialog.getByText(/Ohne BIC entfällt er/);
  await dialog.getByLabel("Währung", { exact: true }).selectOption("EUR");
  await expect(bicHint).toBeVisible();
  await dialog.getByLabel("Währung", { exact: true }).selectOption("CHF");
  await expect(bicHint).toBeHidden();
  await dialog.getByLabel("IBAN", { exact: true }).fill("CH93 0076 2011 6238 5295 7");
  await dialog.getByLabel("QR-IBAN").fill("CH44 3199 9123 0008 8901 2");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Bankkonto gespeichert.")).toBeVisible();
  await expect(page.getByText("CH93 0076 2011 6238 5295 7").first()).toBeVisible();
  await removeAddedAccounts(page);
});

test("a third party's account is chosen per invoice and named on it", async ({
  page,
  isMobile,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Drittkunde ${suffix} AG`);
  try {
    await openApp(page, "/settings?tab=bank-accounts", "Einstellungen");
    await page.getByRole("button", { name: "Konto hinzufügen" }).first().click();
    const dialog = page.getByRole("dialog", { name: /Konto hinzufügen/ });
    await dialog.getByLabel("Bank", { exact: true }).fill("Inkassobank");
    await dialog.getByLabel("Kontoinhaber", { exact: true }).fill("Inkasso AG");
    await dialog.getByLabel("IBAN", { exact: true }).fill("CH58 0079 1123 0008 8901 2");
    // The holder's address appears only for a third party's account, and is required there.
    await expect(dialog.getByLabel("PLZ", { exact: true })).toHaveCount(0);
    await dialog.getByLabel(/Konto gehört einem Dritten/).check();
    await dialog.getByRole("button", { name: "Speichern" }).click();
    await expect(dialog.getByLabel("PLZ", { exact: true })).toHaveAttribute("aria-invalid", "true");
    await dialog.getByLabel(/^Strasse/).fill("Zahlweg");
    await dialog.getByLabel("PLZ", { exact: true }).fill("4001");
    await dialog.getByLabel("Ort", { exact: true }).fill("Basel");
    await expectAccessible(page);
    await dialog.getByRole("button", { name: "Speichern" }).click();
    await expect(page.getByText("Bankkonto gespeichert.")).toBeVisible();
    await expect(page.getByText("Drittkonto", { exact: true })).toBeVisible();

    await openApp(page, `/invoices/new?customer=${customerId}`, "Neue Rechnung");
    const choice = page.getByLabel("Bankverbindung");
    await expect(choice).toHaveValue("");
    await expect(choice.locator("option")).toHaveText([
      "Musterbank · CH93 0076 … (Standard)",
      "Inkasso AG · CH58 0079 … (Drittkonto)",
    ]);
    await choice.selectOption({ label: "Inkasso AG · CH58 0079 … (Drittkonto)" });
    await page.locator("#lines-0-description").fill("Beratung");
    await page.locator("#lines-0-unit_price").fill("100");
    await expectAccessible(page);
    if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
    const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
    await expect(
      paper.getByText(/^Zahlung an: Inkasso AG · IBAN CH58 0079 1123 0008 8901 2$/),
    ).toBeVisible();
  } finally {
    await removeAddedAccounts(page);
  }
});

test("number sequences show a live preview", async ({ page }) => {
  await openApp(page, "/settings?tab=numbering", "Einstellungen");
  const invoices = page.getByRole("region", { name: "Rechnungen", exact: true });
  await expect(invoices.getByText(/R2026\d{4}|R\d{8}/)).toBeVisible();
  await invoices.getByRole("textbox", { name: "Muster" }).fill("RE-{YY}-{NNNNN}");
  await invoices.getByLabel("Nächster Zähler").fill("345");
  await expect(invoices.getByText(/^RE-\d\d-00345$/)).toBeVisible();
  await invoices.getByRole("textbox", { name: "Muster" }).fill("{NNNN}");
  await expect(
    invoices.getByText(
      "Bei jährlichem Zurücksetzen braucht das Muster {YYYY} oder {YY}, sonst wiederholen sich Nummern.",
    ),
  ).toBeVisible();
  await invoices.getByRole("textbox", { name: "Muster" }).fill("R{YYYY}{NNNN}");
  await invoices.getByLabel("Nächster Zähler").fill("1");
  await expectAccessible(page);
});
