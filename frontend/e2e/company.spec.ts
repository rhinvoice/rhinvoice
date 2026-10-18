import { expect, expectAccessible, openApp, test } from "./fixtures";

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
  await dialog.getByLabel("IBAN", { exact: true }).fill("CH93 0076 2011 6238 5295 7");
  await dialog.getByLabel("QR-IBAN").fill("CH44 3199 9123 0008 8901 2");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Bankkonto gespeichert.")).toBeVisible();
  await expect(page.getByText("CH93 0076 2011 6238 5295 7").first()).toBeVisible();
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
