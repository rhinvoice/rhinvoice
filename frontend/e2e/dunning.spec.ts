import { expect, expectAccessible, openApp, test, unique, waitForToastsToClose } from "./fixtures";

test("overdue invoices get payment reminders", async ({ page }, testInfo) => {
  const customer = `Mahnkunde ${unique(testInfo.project.name)} AG`;
  await openApp(page, "/invoices", "Rechnungen");
  await page.getByRole("link", { name: "Mahnwesen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Mahnwesen" })).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: customer });
  // The setup dates the invoice 20 days back; a run across midnight finds it a day later.
  await expect(row.getByText(/^Seit (20|21) Tagen$/)).toBeVisible();
  await expect(row.getByText("Noch keine")).toBeVisible();
  await expectAccessible(page);

  await row.getByRole("button", { name: "Zahlungserinnerung schreiben" }).click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toContainText(customer);
  await expect(confirm).toContainText("Mahngebühr CHF 0.00");
  await expectAccessible(page);
  await confirm.getByRole("button", { name: "Zahlungserinnerung schreiben" }).click();
  await expect(page.getByText("Zahlungserinnerung geschrieben.")).toBeVisible();
  const written = row.getByRole("link", { name: /^Zahlungserinnerung/ });
  await expect(written).toHaveAttribute("href", /^\/api\/reminders\/[0-9a-f-]+\/pdf$/);
  // The next level is not due yet: writing it early needs a confirmation that says so.
  await row.getByRole("button", { name: "1. Mahnung schreiben" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("erst ab");
  await page.getByRole("alertdialog").getByRole("button", { name: "Abbrechen" }).click();
  await waitForToastsToClose(page);
  await expectAccessible(page);

  // The invoice lists its reminders, also once it is paid.
  await row.getByRole("link", { name: /^R\d+/ }).click();
  await page.getByRole("button", { name: "Details" }).click();
  const reminders = page.getByRole("region", { name: "Mahnungen" });
  await expect(reminders.getByRole("link", { name: /^Zahlungserinnerung/ })).toBeVisible();
});

test("the dunning levels are set in the settings", async ({ page }) => {
  await page.goto("/settings?tab=dunning");
  await expect(page.getByRole("tab", { name: "Mahnwesen", selected: true })).toBeVisible();
  const first = page.getByRole("region", { name: "Zahlungserinnerung" });
  await expect(first.getByLabel("Mahngebühr")).toHaveValue("0.00");
  await first.getByLabel("Mahngebühr").fill("12.33");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Bitte die markierten Felder korrigieren.")).toBeVisible();
  await expect(first.getByText("Betrag bis 1000 in Schritten von 0.05")).toBeVisible();
  await expect(first.getByLabel("Mahngebühr")).toHaveAttribute("aria-invalid", "true");
  await expectAccessible(page);
  await first.getByLabel("Mahngebühr").fill("0");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
  await expect(first.getByLabel("Mahngebühr")).toHaveValue("0.00");
});
