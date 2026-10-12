import { createCustomer, expect, expectAccessible, openApp, post, test, unique } from "./fixtures";

test("a recurring invoice is planned, paused and deleted", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerName = `Abokunde ${suffix} AG`;
  await createCustomer(page, customerName);

  await openApp(page, "/invoices", "Rechnungen");
  await page.getByRole("link", { name: "Wiederkehrend", exact: true }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Wiederkehrende Rechnungen" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Neuer Plan" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Neuer Plan" })).toBeVisible();

  // Nothing filled in: the plan's own fields are in the summary too.
  await page.getByRole("button", { name: "Plan anlegen" }).click();
  const summary = page.getByRole("alert").filter({ hasText: "korrigiert werden" });
  await expect(summary.getByRole("link", { name: "Bezeichnung: Bitte ausfüllen." })).toBeVisible();
  await expectAccessible(page);

  await page.getByLabel("Bezeichnung", { exact: true }).first().fill(`Hosting ${suffix}`);
  await page.getByLabel("Intervall").selectOption("quarterly");
  await page.getByRole("combobox", { name: "Kunde suchen" }).fill(`abokunde ${suffix}`);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await page.locator("#lines-0-description").fill("Hosting");
  await page.locator("#lines-0-unit_price").fill("29");
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await page.getByRole("button", { name: "Plan anlegen" }).click();
  await expect(page.getByText("Plan angelegt.")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: `Hosting ${suffix}` })).toBeVisible();
  const status = page.getByRole("region", { name: "Stand" });
  await expect(status.getByText(/^Nächste Rechnung am /)).toBeVisible();
  await expect(status.getByText("Aktiv")).toBeVisible();
  await expect(status.getByText("Noch keine Rechnung geschrieben.")).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("button", { name: "Pausieren" }).click();
  await expect(page.getByText("Plan pausiert.")).toBeVisible();
  await expect(status.getByText("Pausiert", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Wiederkehrende Rechnungen" }).click();
  // A table row on wide screens, a card on phones.
  const entry = page.locator("tr, li").filter({ hasText: `Hosting ${suffix}`, visible: true });
  await expect(entry.getByText(/Vierteljährlich/)).toBeVisible();
  await expect(entry.getByText("Pausiert")).toBeVisible();
  await expectAccessible(page);

  await entry.getByRole("link", { name: new RegExp(`Hosting ${suffix}`) }).click();
  await page.getByRole("button", { name: "Plan löschen" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Plan löschen" }).click();
  await expect(page.getByText(`Plan «Hosting ${suffix}» gelöscht.`)).toBeVisible();
  await expect(page.getByText(`Hosting ${suffix}`)).toHaveCount(0);
});

test("an invoice is made recurring", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Wartungskunde ${suffix} AG`);
  const invoice = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    subject: `Wartung ${suffix}`,
    lines: [{ description: "Wartungspauschale", quantity: "1", unit: "LS", unit_price: "450" }],
  });
  await post(page, `/api/documents/${invoice.id}/issue`, {});
  await page.goto(`/documents/${invoice.id}`);
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Wiederkehrend machen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Neuer Plan" })).toBeVisible();
  await expect(page.getByLabel("Bezeichnung", { exact: true }).first()).toHaveValue(
    `Wartung ${suffix}`,
  );
  await expect(
    page.getByRole("button", { name: "Position 1 bearbeiten: Wartungspauschale" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Plan anlegen" }).click();
  await expect(page.getByText("Plan angelegt.")).toBeVisible();
});
