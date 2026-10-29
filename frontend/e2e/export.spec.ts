import { readFile } from "node:fs/promises";

import {
  createCustomer,
  expect,
  expectAccessible,
  isoDaysFromToday,
  openApp,
  post,
  test,
  unique,
} from "./fixtures";

test("the invoices of a period are exported for the bookkeeping", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const customer = `Buchhaltung ${unique(testInfo.project.name)} AG`;
  const customerId = await createCustomer(page, customer);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "2", unit: "HUR", unit_price: "100" }],
  });
  const invoice = await post<{ number: string }>(page, `/api/documents/${draft.id}/issue`, {});

  await openApp(page, "/invoices", "Rechnungen");
  await page.getByRole("button", { name: "Exportieren" }).click();
  const dialog = page.getByRole("dialog", { name: "Rechnungen exportieren" });
  // The previous full month as Excel is the default.
  await expect(dialog.getByRole("radio", { name: "Monat" })).toBeChecked();
  await expect(dialog.getByRole("radio", { name: "Excel" })).toBeChecked();
  const lastMonth = new Date(`${isoDaysFromToday(0).slice(0, 8)}01T00:00:00Z`);
  lastMonth.setUTCDate(0);
  await expect(dialog.getByRole("combobox", { name: "Monat" })).toHaveValue(
    String(lastMonth.getUTCMonth() + 1),
  );
  await expect(dialog.getByRole("combobox", { name: "Jahr" })).toHaveValue(
    String(lastMonth.getUTCFullYear()),
  );
  await expectAccessible(page);
  await expect(dialog).toHaveScreenshot("export-dialog.png", {
    // Month and year follow the day of the test.
    mask: [
      dialog.getByRole("combobox", { name: "Monat" }),
      dialog.getByRole("combobox", { name: "Jahr" }),
    ],
  });

  // A free period that ends before it starts cannot be downloaded.
  await dialog.getByRole("radio", { name: "Frei" }).check();
  await dialog.getByLabel("Von").fill(isoDaysFromToday(0));
  await dialog.getByLabel("Bis").fill(isoDaysFromToday(-1));
  await expect(dialog.getByText("Das Ende liegt vor dem Anfang.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Herunterladen" })).toBeDisabled();
  await expectAccessible(page);

  // Today as CSV: the invoice is in the list, with the company's decimal point.
  await dialog.getByLabel("Bis").fill(isoDaysFromToday(0));
  await dialog.getByRole("radio", { name: "CSV" }).check();
  const [csv] = await Promise.all([
    page.waitForEvent("download"),
    dialog.getByRole("button", { name: "Herunterladen" }).click(),
  ]);
  const today = isoDaysFromToday(0);
  expect(csv.suggestedFilename()).toBe(`Rechnungen ${today}_${today}.csv`);
  const content = await readFile(await csv.path(), "utf8");
  // UTF-8 with BOM, so that Excel reads the umlauts right.
  expect(content.charCodeAt(0)).toBe(0xfeff);
  expect(content.slice(1).startsWith("Nummer;Art;Datum;")).toBe(true);
  const line = content.split("\r\n").find((row) => row.startsWith(`${invoice.number};`));
  expect(line).toContain(`;Rechnung;${today};`);
  expect(line).toContain(`;${customer};CH;`);
  expect(line).toContain(";200.00;");
  await expect(dialog).toBeHidden();

  // With the PDFs everything comes as one ZIP.
  await page.getByRole("button", { name: "Exportieren" }).click();
  const again = page.getByRole("dialog", { name: "Rechnungen exportieren" });
  await again.getByRole("radio", { name: "Frei" }).check();
  await again.getByLabel("Von").fill(today);
  await again.getByLabel("Bis").fill(today);
  await again.getByLabel("Rechnungs-PDFs als ZIP beilegen").check();
  const [zip] = await Promise.all([
    page.waitForEvent("download"),
    again.getByRole("button", { name: "Herunterladen" }).click(),
  ]);
  expect(zip.suggestedFilename()).toBe(`Rechnungen ${today}_${today}.zip`);
  const archive = await readFile(await zip.path());
  // A ZIP starts with "PK" and names its files in plain text.
  expect(archive.subarray(0, 2).toString()).toBe("PK");
  expect(archive.includes(Buffer.from(`${invoice.number}.pdf`))).toBe(true);
  expect(archive.includes(Buffer.from(`Rechnungen ${today}_${today}.xlsx`))).toBe(true);
});
