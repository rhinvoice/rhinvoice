import {
  createCustomer,
  expect,
  expectAccessible,
  openApp,
  post,
  test,
  unique,
  waitForToastsToClose,
} from "./fixtures";

interface Line {
  readonly description: string;
  readonly in_total: string;
  readonly alternative_to: string | null;
}

test("a quote offers an alternative and an option; the invoice takes what was chosen", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(90_000);
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Optionen ${suffix} AG`);
  const quote = await post<{ id: string }>(page, "/api/documents", {
    type: "quote",
    customer_id: customerId,
    subject: "Website",
    lines: [
      { description: "Design und Umsetzung", quantity: "1", unit: "LS", unit_price: "4000" },
      { description: "Hosting 1 Jahr, Paket S", quantity: "1", unit: "ANN", unit_price: "300" },
      { description: "Hosting 1 Jahr, Paket L", quantity: "1", unit: "ANN", unit_price: "600" },
      { description: "Mehrsprachigkeit FR/IT", quantity: "1", unit: "LS", unit_price: "1200" },
    ],
  });
  await openApp(page, `/documents/${quote.id}`, "Angebot (Entwurf)");

  // Paket L replaces Paket S; only the other items in the total are offered.
  await page.getByRole("button", { name: /^Position 3 bearbeiten/ }).click();
  const inTotal = page.locator("#lines-2-in_total");
  await expect(inTotal.locator("option")).toHaveText([
    "Ja",
    "Optional",
    "Alternative zu Pos. 1",
    "Alternative zu Pos. 2",
    "Alternative zu Pos. 4",
  ]);
  await inTotal.selectOption({ label: "Alternative zu Pos. 2" });
  await expect(inTotal).toHaveAccessibleDescription(
    "Nicht im Total: Der Betrag steht im PDF in Klammern.",
  );
  await expectAccessible(page);
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await page.getByRole("button", { name: /^Position 4 bearbeiten/ }).click();
  await page.locator("#lines-3-in_total").selectOption({ label: "Optional" });
  await page.getByRole("button", { name: "Übernehmen" }).click();

  await expect(page.getByRole("button", { name: /^Position 3 bearbeiten/ })).toContainText(
    "Alternative zu 2",
  );
  await expect(page.getByRole("button", { name: /^Position 4 bearbeiten/ })).toContainText(
    "Optional",
  );
  // Only design and Paket S count: 4300 + 8.1 % VAT.
  await expect(
    page
      .getByText(/^CHF\s4.648\.30$/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Angebot"]');
  await expect(paper.locator("tr.not-in-total")).toHaveCount(2);
  await expect(paper.locator("tr.not-in-total").first()).toContainText("Alternative zu Pos. 2");
  await expect(paper.locator("tr.not-in-total").first()).toContainText("(600.00)");
  await expect(paper.locator("tr.not-in-total").last()).toContainText("Optional");
  await expect(paper.locator("tr.not-in-total").last()).toContainText(/\(1.200\.00\)/);
  await expect(paper.getByText("Beträge in Klammern sind nicht im Total enthalten.")).toBeVisible();
  await expect(paper.locator(".value.grand")).toHaveText(/4.648\.30/);
  if (isMobile) await page.getByRole("button", { name: "Bearbeiten" }).click();
  await waitForToastsToClose(page);
  // Away from the lines: a line under the pointer is highlighted.
  await page.mouse.move(0, 0);
  await expect(page.getByRole("region", { name: "Positionen" })).toHaveScreenshot(
    "optional-items-lines.png",
  );

  // When Paket S stops counting, its alternative becomes an option.
  await page.getByRole("button", { name: /^Position 2 bearbeiten/ }).click();
  await page.locator("#lines-1-in_total").selectOption({ label: "Optional" });
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(page.getByRole("button", { name: /^Position 3 bearbeiten/ })).toContainText(
    "Optional",
  );
  await page.getByRole("button", { name: /^Position 2 bearbeiten/ }).click();
  await page.locator("#lines-1-in_total").selectOption({ label: "Ja" });
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await page.getByRole("button", { name: /^Position 3 bearbeiten/ }).click();
  await page.locator("#lines-2-in_total").selectOption({ label: "Alternative zu Pos. 2" });
  await page.getByRole("button", { name: "Übernehmen" }).click();

  // Sent, the quote is turned into an invoice with the items the customer took.
  await page.getByRole("button", { name: "Als versendet markieren" }).click();
  await page
    .getByRole("alertdialog", { name: "Angebot als versendet markieren?" })
    .getByRole("button", { name: "Als versendet markieren" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: /^Angebot \S+$/ })).toBeVisible();
  // Only a sent quote offers the conversion: wait for its actions before opening the menu.
  await expect(page.getByRole("button", { name: "Angenommen" })).toBeVisible();
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "In Rechnung umwandeln" }).click();
  const dialog = page.getByRole("dialog", { name: "Positionen für die Rechnung" });
  const design = dialog.getByRole("checkbox", { name: /Design und Umsetzung/ });
  const small = dialog.getByRole("checkbox", { name: /Paket S/ });
  const large = dialog.getByRole("checkbox", { name: /Paket L/ });
  const extra = dialog.getByRole("checkbox", { name: /Mehrsprachigkeit/ });
  await expect(design).toBeChecked();
  await expect(small).toBeChecked();
  await expect(large).not.toBeChecked();
  await expect(extra).not.toBeChecked();
  await expect(dialog.getByText(/^Rechnung: CHF\s4.648\.30$/)).toBeVisible();
  // The customer took Paket L instead of Paket S, and the option.
  await small.uncheck();
  await large.check();
  await extra.check();
  // 4000 + 600 + 1200 + 8.1 % VAT.
  await expect(dialog.getByText(/^Rechnung: CHF\s6.269\.80$/)).toBeVisible();
  await expectAccessible(page);
  await page.mouse.move(0, 0);
  await expect(dialog).toHaveScreenshot("optional-items-convert.png");
  await dialog.getByRole("button", { name: "Rechnung erstellen" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  const invoiceId = page.url().split("/").pop() ?? "";
  const invoice = (await (await page.request.get(`/api/documents/${invoiceId}`)).json()) as {
    lines: Line[];
  };
  expect(
    invoice.lines.map((line) => [line.description, line.in_total, line.alternative_to]),
  ).toEqual([
    ["Design und Umsetzung", "yes", null],
    ["Hosting 1 Jahr, Paket L", "yes", null],
    ["Mehrsprachigkeit FR/IT", "yes", null],
  ]);
  // An invoice has no In total choice.
  await page.getByRole("button", { name: /^Position 1 bearbeiten/ }).click();
  await expect(page.locator("#lines-0-in_total")).toHaveCount(0);
});

test("the editor numbers positions as the PDF does", async ({ page, isMobile }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Nummern ${suffix} AG`);
  const quote = await post<{ id: string }>(page, "/api/documents", {
    type: "quote",
    customer_id: customerId,
    subject: "Website",
    lines: [
      { kind: "text", description: "Phase 1" },
      { description: "Design und Umsetzung", quantity: "1", unit: "LS", unit_price: "4000" },
      {
        description: "Domaingebühr",
        quantity: "1",
        unit: "ANN",
        unit_price: "20",
        pass_through: true,
      },
      { description: "Hosting 1 Jahr, Paket S", quantity: "1", unit: "ANN", unit_price: "300" },
      { description: "Hosting 1 Jahr, Paket L", quantity: "1", unit: "ANN", unit_price: "600" },
    ],
  });
  await openApp(page, `/documents/${quote.id}`, "Angebot (Entwurf)");

  // Neither the heading nor the pass-through fee has a number, in the editor as in the PDF.
  await expect(page.getByRole("button", { name: "Zeile bearbeiten: Phase 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Zeile bearbeiten: Domaingebühr" })).toBeVisible();
  await page
    .getByRole("button", { name: "Position 3 bearbeiten: Hosting 1 Jahr, Paket L" })
    .click();
  const inTotal = page.locator("#lines-4-in_total");
  await expect(inTotal.locator("option")).toHaveText([
    "Ja",
    "Optional",
    "Alternative zu Pos. 1",
    "Alternative zu «Domaingebühr»",
    "Alternative zu Pos. 2",
  ]);
  await inTotal.selectOption({ label: "Alternative zu Pos. 2" });
  await expectAccessible(page);
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(
    page.getByRole("button", { name: "Position 3 bearbeiten: Hosting 1 Jahr, Paket L" }),
  ).toContainText("Alternative zu 2");

  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Angebot"]');
  await expect(paper.locator("tr.not-in-total")).toContainText("Hosting 1 Jahr, Paket L");
  await expect(paper.locator("tr.not-in-total")).toContainText("Alternative zu Pos. 2");
});
