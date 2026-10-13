import {
  createCustomer,
  expect,
  expectAccessible,
  isoDaysFromToday,
  openApp,
  post,
  test,
  unique,
  waitForToastsToClose,
} from "./fixtures";

test("an invoice that will not be paid is written off", async ({ page }, testInfo) => {
  const customer = `Zahlungsunfähig ${unique(testInfo.project.name)} AG`;
  const customerId = await createCustomer(page, customer);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "2", unit: "HUR", unit_price: "100" }],
  });
  const invoice = await post<{ number: string }>(page, `/api/documents/${draft.id}/issue`, {});

  await page.goto(`/documents/${draft.id}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(invoice.number);
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Abschreiben …" }).click();
  const dialog = page.getByRole("dialog", { name: `Rechnung ${invoice.number} abschreiben` });
  await expect(dialog).toContainText("Die Rechnung bleibt unverändert");
  await expect(dialog).toContainText("Offener BetragCHF 216.20");
  // The company is Swiss: the hint names the Swiss rule.
  await expect(dialog).toContainText("Art. 41 MWSTG");
  const date = dialog.getByLabel("Abgeschrieben per");
  await expect(date).toHaveValue(isoDaysFromToday(0));
  // A day in the future is refused in the form.
  await date.fill(isoDaysFromToday(1));
  await dialog.getByRole("button", { name: "Abschreiben", exact: true }).click();
  await expect(
    dialog.getByText("Das Datum liegt zwischen dem Rechnungsdatum und heute."),
  ).toBeVisible();
  await expectAccessible(page);
  // The invoice is of this year: its end is today at the latest.
  await dialog.getByRole("button", { name: "Ende Rechnungsjahr" }).click();
  await expect(date).toHaveValue(isoDaysFromToday(0));
  await dialog.getByLabel("Grund").selectOption({ label: "Verjährt" });
  await dialog.getByLabel("Notiz").fill("Mahnungen ohne Antwort");
  await dialog.getByRole("button", { name: "Abschreiben", exact: true }).click();
  await expect(page.getByText("Rechnung abgeschrieben.")).toBeVisible();
  await expect(page.getByText("Abgeschrieben", { exact: true }).first()).toBeVisible();
  // Nothing more to collect: no "paid" button, but a payment can still come in.
  await expect(page.getByRole("button", { name: "Als bezahlt markieren" })).toBeHidden();
  await waitForToastsToClose(page);

  await page.getByRole("button", { name: "Details" }).click();
  const writeOff = page.getByRole("region", { name: "Abschreibung" });
  await expect(writeOff).toContainText("CHF 216.20");
  await expect(writeOff).toContainText("Darin enthaltene MWST");
  await expect(writeOff).toContainText("CHF 16.20");
  await expect(writeOff).toContainText("Verjährt");
  await expect(writeOff).toContainText("Mahnungen ohne Antwort");
  await expect(page.getByRole("region", { name: "Verlauf" })).toContainText("Verjährt");
  await expectAccessible(page);

  // The list has a view for it, with the losses per year.
  await openApp(page, "/invoices?view=written_off", "Rechnungen");
  await page.getByRole("searchbox", { name: "Dokumente durchsuchen" }).fill(customer);
  const row = page.getByRole("row").filter({ hasText: customer });
  await expect(row.getByText("Abgeschrieben").filter({ visible: true }).first()).toBeVisible();
  const losses = page.getByRole("region", { name: "Debitorenverluste" });
  await expect(losses).toContainText(isoDaysFromToday(0).slice(0, 4));
  await expectAccessible(page);

  // The customer pays a part after all: the invoice stays written off for the rest.
  await page.goto(`/documents/${draft.id}`);
  await page.getByRole("button", { name: "Zahlung erfassen" }).click();
  const payment = page.getByRole("dialog", { name: "Zahlung erfassen" });
  await expect(payment).toContainText("Abgeschrieben: CHF 216.20");
  await payment.getByLabel("Betrag in CHF").fill("16.20");
  await payment.getByRole("button", { name: "Zahlung speichern" }).click();
  await expect(page.getByText("Zahlung über CHF 16.20 erfasst.")).toBeVisible();
  await waitForToastsToClose(page);
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("region", { name: "Zahlungen" })).toContainText(
    "Nach der Abschreibung eingegangen",
  );
  await expect(page.getByRole("region", { name: "Summen" })).toContainText(
    "AbgeschriebenCHF 200.00",
  );

  // Written off by mistake: taking it back reopens the rest.
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Abschreibung zurücknehmen" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Abschreibung zurücknehmen?" });
  await expectAccessible(page);
  await confirm.getByRole("button", { name: "Abschreibung zurücknehmen" }).click();
  await expect(page.getByText("Abschreibung zurückgenommen.")).toBeVisible();
  await expect(page.getByText("Teilweise bezahlt", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Abschreibung" })).toBeHidden();
});
