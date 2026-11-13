import {
  HEADERS,
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

test.describe.configure({ mode: "serial" });

interface TaxRate {
  readonly id: string;
  readonly name: string;
  readonly preset: string | null;
}

/** The day as the interface shows it in de-CH, e.g. "12.12.2026". */
function swissDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day ?? ""}.${month ?? ""}.${year ?? ""}`;
}

test("own tax rates: checked as typed, changed from a date, chosen in a line, hidden", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(90_000);
  const name = `Weinbau ${unique(testInfo.project.name)}`;
  await openApp(page, "/settings?tab=tax-rates", "Einstellungen");
  await expect(page.getByRole("heading", { level: 2, name: "Steuersätze" })).toBeVisible();

  // The rates of the Swiss company: today's percentage and the one before it.
  const standard = page.getByRole("row", { name: /^Normalsatz/ });
  await expect(standard).toContainText("seit 01.01.2024 · vorher 7.7%");
  await expect(standard).toContainText("8.1%");
  await expect(page.getByRole("row", { name: /^Von der Steuer ausgenommen/ })).toContainText(
    "Grund: Steuerbefreite Leistung",
  );
  await expectAccessible(page);

  // A rate in use is hidden, not deleted; its category stays.
  await page.getByRole("button", { name: "Normalsatz", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Steuersatz bearbeiten" });
  await expect(edit.getByLabel("Art für die E-Rechnung")).toBeDisabled();
  await expect(edit.getByLabel("Prozentsatz")).toHaveValue("8.1");
  await expect(edit.getByLabel("Prozentsatz")).toHaveAccessibleDescription("gültig ab 01.01.2024");
  await expect(edit.getByText("Wird verwendet: ausblenden statt löschen.")).toBeVisible();
  await expect(edit.getByRole("button", { name: "Löschen" })).toHaveCount(0);
  await edit.getByRole("button", { name: "Verlauf anzeigen" }).click();
  const history = edit.getByRole("list", { name: "Verlauf" });
  await expect(history.getByRole("listitem")).toHaveText([
    /ab 01\.01\.2011\s*8%/,
    /ab 01\.01\.2018\s*7\.7%/,
    /ab 01\.01\.2024\s*8\.1%/,
  ]);
  await expectAccessible(page);
  await expect(edit).toHaveScreenshot("tax-rate-dialog.png");
  await edit.getByRole("button", { name: "Abbrechen" }).click();
  // The server refuses to delete it as well.
  const rates = (await (await page.request.get("/api/tax-rates")).json()) as TaxRate[];
  const used = rates.find((rate) => rate.preset === "standard");
  const refused = await page.request.delete(`/api/tax-rates/${used?.id ?? ""}`, {
    headers: HEADERS,
  });
  expect(refused.status()).toBe(409);
  const { error } = (await refused.json()) as { error: { code: string } };
  expect(error.code).toBe("tax_rate_in_use");

  // A new rate: the category is checked against the percentage while typing.
  await page.getByRole("button", { name: "Neuer Satz" }).click();
  const add = page.getByRole("dialog", { name: "Neuer Steuersatz" });
  await expect(add.getByLabel("Art für die E-Rechnung")).toHaveValue("S");
  await add.getByLabel("Name").fill(name);
  await add.getByLabel("Prozentsatz").fill("0");
  await expect(add.getByLabel("Prozentsatz")).toHaveAccessibleDescription(
    "Steuerpflichtig (S) braucht einen Prozentsatz über 0 %.",
  );
  await add.getByLabel("Prozentsatz").fill("5.5");
  await add.getByLabel("Art für die E-Rechnung").selectOption("E");
  await expect(add.getByLabel("Prozentsatz")).toHaveAccessibleDescription(
    "Nullsatz (Z) und Steuerfrei (E) brauchen 0 %.",
  );
  await expect(add.getByLabel("Befreiungsgrund")).toBeVisible();
  await add.getByLabel("Art für die E-Rechnung").selectOption("S");
  await expect(add.getByLabel("Befreiungsgrund")).toHaveCount(0);
  await add.getByLabel("Hinweis auf der Rechnung").fill("Weinbau nach eigener Regel");
  await expectAccessible(page);
  // Keyboard: on phones a tap would leave the pointer on the toast, which then stays open.
  await add.getByRole("button", { name: "Speichern" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Steuersatz «${name}» gespeichert.`)).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(`^${name}`) });
  await expect(row).toContainText("5.5%");
  await expect(row).toContainText("Weinbau nach eigener Regel");

  // A new percentage from a date to come: today's stays, the list names the change.
  const from = isoDaysFromToday(30);
  await page.getByRole("button", { name, exact: true }).click();
  const change = page.getByRole("dialog", { name: "Steuersatz bearbeiten" });
  await change.getByRole("button", { name: "Satz ändern ab Datum …" }).click();
  const value = page.getByRole("dialog", { name: "Satz ändern ab Datum" });
  await value.getByLabel("Gültig ab").fill(from);
  await value.getByLabel("Prozentsatz").fill("0");
  await value.getByRole("button", { name: "Hinzufügen" }).click();
  await expect(value.getByLabel("Prozentsatz")).toHaveAccessibleDescription(
    "Steuerpflichtig (S) braucht einen Prozentsatz über 0 %.",
  );
  await value.getByLabel("Prozentsatz").fill("6.5");
  await value.getByRole("button", { name: "Hinzufügen" }).click();
  await expect(value).toHaveCount(0);
  await expect(change.getByRole("list", { name: "Verlauf" }).getByRole("listitem")).toHaveCount(2);
  await expect(change.getByLabel("Prozentsatz")).toHaveValue("5.5");
  await change.getByRole("button", { name: "Speichern" }).focus();
  await page.keyboard.press("Enter");
  await expect(row).toContainText(`ab ${swissDate(from)}: 6.5%`);
  await expect(row).toContainText("5.5%");
  await waitForToastsToClose(page);

  // In a line, the rate shows its percentage on the date of supply.
  const customerId = await createCustomer(page, `Steuersatz ${unique(testInfo.project.name)} AG`);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Rebschnitt", quantity: "1", unit: "HUR", unit_price: "100" }],
  });
  await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
  const line = page.getByRole("button", { name: /^Position 1 bearbeiten/ });
  await expect(line).toContainText("8.1%");
  await line.click();
  const tax = page.locator("#lines-0-tax");
  await expect(tax.locator("option:checked")).toHaveText("Normalsatz – 8.1%");
  // Grouped into taxable and without tax, the pass-through item last.
  const groups = tax.locator("optgroup");
  await expect(groups.nth(0)).toHaveAttribute("label", "Steuerpflichtig");
  await expect(groups.nth(0)).toContainText("Reduzierter Satz – 2.6%");
  await expect(groups.nth(1)).toHaveAttribute("label", "Ohne Steuer");
  await expect(groups.nth(1).locator("option").last()).toHaveText(
    "Durchlaufender Posten (ohne MWST)",
  );
  await tax.selectOption({ label: `${name} – 5.5%` });
  await expectAccessible(page);
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(line).toContainText("5.5%");
  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
  await expect(paper.getByText("MWST 5.5 % auf 100.00")).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Bearbeiten" }).click();
  // The draft saves itself; then the rate is in use.
  const own = (await (await page.request.get("/api/tax-rates")).json()) as TaxRate[];
  const rateId = own.find((rate) => rate.name === name)?.id;
  await expect
    .poll(async () => {
      const saved = (await (await page.request.get(`/api/documents/${draft.id}`)).json()) as {
        lines: { tax_rate_id: string | null }[];
      };
      return saved.lines[0]?.tax_rate_id;
    })
    .toBe(rateId);

  // Hidden, the rate is offered no more; the line that uses it keeps it.
  await openApp(page, "/settings?tab=tax-rates", "Einstellungen");
  await page.getByRole("button", { name, exact: true }).click();
  const hide = page.getByRole("dialog", { name: "Steuersatz bearbeiten" });
  await expect(hide.getByText("Wird verwendet: ausblenden statt löschen.")).toBeVisible();
  await hide.getByRole("button", { name: "Ausblenden" }).click();
  await expect(page.getByText(`«${name}» ausgeblendet`, { exact: false })).toBeVisible();
  await expect(hide.getByRole("button", { name: "Einblenden" })).toBeVisible();
  await hide.getByRole("button", { name: "Abbrechen" }).click();
  await expect(page.getByRole("button", { name: `${name} (ausgeblendet)` })).toBeVisible();
  await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
  await page.getByRole("button", { name: /^Position 1 bearbeiten/ }).click();
  await expect(tax.locator("option:checked")).toHaveText(`${name} (ausgeblendet) – 5.5%`);
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await expect(page.locator("#lines-0-tax option", { hasText: name })).toHaveCount(0);
});

test("a preset is taken over again after deleting its rate", async ({ page }) => {
  const zero = "0 % (steuerbar)";
  await openApp(page, "/settings?tab=tax-rates", "Einstellungen");
  // Nothing uses the zero rate: it can be deleted.
  await page.getByRole("button", { name: zero, exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Steuersatz bearbeiten" });
  await edit.getByRole("button", { name: "Löschen" }).click();
  const confirm = page.getByRole("alertdialog", { name: `«${zero}» löschen?` });
  await confirm.getByRole("button", { name: "Löschen" }).click();
  await expect(page.getByText(`«${zero}» gelöscht.`)).toBeVisible();
  await expect(page.getByRole("button", { name: zero, exact: true })).toHaveCount(0);

  // The presets of the country offer it again, with its percentage.
  await page.getByRole("button", { name: "Aus Vorlage …" }).click();
  const presets = page.getByRole("dialog", { name: "Aus Vorlage übernehmen" });
  const preset = presets.getByRole("listitem", { name: zero });
  await expect(preset).toContainText("0%");
  await expectAccessible(page);
  await preset.getByRole("button", { name: `${zero} übernehmen` }).click();
  await expect(page.getByText(`«${zero}» übernommen.`)).toBeVisible();
  await expect(presets).toHaveCount(0);
  await expect(
    page.getByRole("row", { name: new RegExp(`^${zero.replace(/[()]/g, "\\$&")}`) }),
  ).toContainText("Z");

  // Taken over, it is offered no more.
  await page.getByRole("button", { name: "Aus Vorlage …" }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Aus Vorlage übernehmen" })
      .getByText("Alle Vorlagen für Ihr Land sind schon übernommen."),
  ).toBeVisible();
});
